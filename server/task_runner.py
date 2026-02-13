import logging
import os
import json
import random
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable

from server.coreApi.MainLogicApi import ApiClient
from server.coreApi.AiServiceClient import generate_article
from server.util.Config import ConfigManager
from server.util.MessagePush import MessagePusher
from server.util.HelperFunctions import desensitize_name, is_holiday
from server.util.FileUploader import upload_img
from server.util.LoggerContext import _log_ctx

logger = logging.getLogger("server.task_runner")

def perform_clock_in(
    api_client: ApiClient, config: ConfigManager, forced_checkin_type: Optional[str] = None
) -> Dict[str, Any]:
    """执行打卡操作"""
    try:
        current_time = datetime.now()
        current_hour = current_time.hour
        address = config.get_value("config.clockIn.location.address")

        # 确定打卡类型
        if forced_checkin_type in ("START", "END"):
            checkin_type = forced_checkin_type
            display_type = "上班" if checkin_type == "START" else "下班"
        else:
            if current_hour < 12:
                checkin_type = "START"
                display_type = "上班"
            else:
                checkin_type = "END"
                display_type = "下班"

        # 检查配置：是否跳过节假日/自定义日期
        clock_in_mode = config.get_value("config.clockIn.mode")
        special_clock_in = config.get_value("config.clockIn.specialClockIn")

        should_skip = False
        skip_message = ""

        if clock_in_mode == "holiday" and is_holiday(current_time):
            if not special_clock_in:
                should_skip = True
                skip_message = "今天是休息日，已跳过打卡"
            else:
                checkin_type = "HOLIDAY"
                display_type = "休息/节假日"

        elif clock_in_mode == "custom":
            today_weekday = current_time.weekday() + 1
            custom_days = config.get_value("config.clockIn.customDays") or []
            if today_weekday not in custom_days:
                if not special_clock_in:
                    should_skip = True
                    skip_message = "今天不在设置打卡时间范围内，已跳过打卡"
                else:
                    checkin_type = "HOLIDAY"
                    display_type = "休息/节假日"

        if should_skip:
            return {
                "status": "skip",
                "message": skip_message,
                "task_type": "打卡",
                "details": {
                    "打卡类型": display_type,
                    "打卡时间": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "打卡地点": address,
                },
            }

        last_checkin_info = api_client.get_checkin_info()

        # 检查是否已经打过卡
        if last_checkin_info and last_checkin_info.get("type") == checkin_type:
            create_time_str = last_checkin_info.get("createTime")
            if create_time_str:
                last_checkin_time = datetime.strptime(
                    create_time_str, "%Y-%m-%d %H:%M:%S"
                )
                if last_checkin_time.date() == current_time.date():
                    logger.info(f"今日 {display_type} 卡已打，无需重复打卡")
                    return {
                        "status": "skip",
                        "message": f"今日 {display_type} 卡已打，无需重复打卡",
                        "task_type": "打卡",
                        "details": {
                            "打卡类型": display_type,
                            "上次打卡时间": create_time_str,
                            "打卡地点": address,
                        },
                    }

        user_name = desensitize_name(config.get_value("userInfo.nikeName"))
        logger.info(f"用户 {user_name} 开始 {display_type} 打卡")

        # 打卡图片和备注
        img_count = config.get_value("config.clockIn.imageCount")
        if not isinstance(img_count, int) or img_count < 0:
            img_count = 1
            
        attachments = upload_img(
            api_client.get_upload_token(),
            config.get_value("userInfo.orgJson.snowFlakeId"),
            config.get_value("userInfo.userId"),
            img_count,
        )

        description_list = config.get_value("config.clockIn.description")
        description = random.choice(description_list) if description_list else None

        # 设置打卡信息
        checkin_info = {
            "type": checkin_type,
            "lastDetailAddress": last_checkin_info.get("address"),
            "attachments": attachments or None,
            "description": description,
        }

        api_client.submit_clock_in(checkin_info)
        logger.info(f"用户 {user_name} {display_type} 打卡成功")

        return {
            "status": "success",
            "message": f"{display_type}打卡成功",
            "task_type": "打卡",
            "details": {
                "姓名": config.get_value("userInfo.nikeName"),
                "打卡类型": display_type,
                "打卡时间": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "打卡地点": address,
            },
        }
    except Exception as e:
        logger.error(f"打卡失败: {e}")
        err = str(e) or "unknown"
        tips = []
        if "clockIn.location.address" in err:
            tips.append("请先在用户配置中填写打卡地址，或使用“账号地址填充”")
        if "planId" in err:
            tips.append("请先获取并保存 planId（非教师账号需要）")
        if "token" in err or "Token" in err:
            tips.append("账号 token 失效时会自动重登；如持续失败请检查账号/密码")
        details = {
            "姓名": config.get_value("userInfo.nikeName"),
            "打卡时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "打卡地点": config.get_value("config.clockIn.location.address"),
        }
        if tips:
            details["建议"] = "；".join(tips)
        return {"status": "fail", "message": f"打卡失败: {err}", "task_type": "打卡", "details": details}


def _submit_report_common(
    api_client: ApiClient,
    config: ConfigManager,
    report_type: str,
    title_func: Callable[[int], str],
    check_time_func: Callable[[datetime], bool],
    get_submitted_func: Callable[[], Dict[str, Any]],
    paper_num_key: str,
    image_count_key: str,
    task_name: str,
    form_type: int,
) -> Dict[str, Any]:
    """通用日报/周报/月报提交逻辑"""

    # 映射 report_type 到 config key
    config_key_map = {"day": "daily", "week": "weekly", "month": "monthly"}
    config_key = config_key_map.get(report_type)

    if not config.get_value(f"config.reportSettings.{config_key}.enabled"):
        logger.info(f"用户未开启{task_name}功能，跳过")
        now = datetime.now()
        return {
            "status": "skip",
            "message": f"用户未开启{task_name}功能",
            "task_type": task_name,
            "details": {
                "提交时间": now.strftime("%Y-%m-%d %H:%M:%S"),
                "开关": "未开启",
            },
        }

    current_time = datetime.now()

    # 检查提交时间
    if not check_time_func(current_time):
        logger.info(f"未到{task_name}提交时间")
        return {
            "status": "skip",
            "message": f"未到{task_name}提交时间",
            "task_type": task_name,
            "details": {
                "提交时间": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "开关": "已开启",
            },
        }

    try:
        # 检查是否已提交
        submitted_reports_info = get_submitted_func()
        submitted_reports = submitted_reports_info.get("data", [])

        count = submitted_reports_info.get("flag", 0) + 1
        title = title_func(count)

        if submitted_reports:
            last_report = submitted_reports[0]
            should_skip = False

            if report_type == "day":
                last_time = datetime.strptime(
                    last_report["createTime"], "%Y-%m-%d %H:%M:%S"
                )
                if last_time.date() == current_time.date():
                    should_skip = True
            elif report_type == "week":
                current_week_info = api_client.get_weeks_date()[0]
                current_week_str = f"第{count}周"
                if last_report.get("weeks") == current_week_str:
                    should_skip = True
            elif report_type == "month":
                current_yearmonth = current_time.strftime("%Y-%m")
                if last_report.get("yearmonth") == current_yearmonth:
                    should_skip = True

            if should_skip:
                logger.info(f"本周期已经提交过{task_name}，跳过")
                return {
                    "status": "skip",
                    "message": f"本周期已经提交过{task_name}",
                    "task_type": task_name,
                }

        # 生成内容
        job_info = api_client.get_job_info()
        content = generate_article(
            config,
            title,
            job_info,
            config.get_value(paper_num_key),
        )

        # 上传图片
        img_count = config.get_value(image_count_key)
        if not isinstance(img_count, int) or img_count < 0:
            img_count = 1

        attachments = upload_img(
            api_client.get_upload_token(),
            config.get_value("userInfo.orgJson.snowFlakeId"),
            config.get_value("userInfo.userId"),
            img_count,
        )

        report_info = {
            "title": title,
            "content": content,
            "attachments": attachments,
            "reportType": report_type,
            "jobId": job_info.get("jobId", None),
            "reportTime": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "formFieldDtoList": api_client.get_from_info(form_type),
        }

        # 特定类型的额外字段
        extra_details = {}
        if report_type == "week":
            current_week_info = api_client.get_weeks_date()[0]
            report_info["startTime"] = current_week_info.get("startTime")
            report_info["endTime"] = current_week_info.get("endTime")
            report_info["weeks"] = f"第{count}周"
            extra_details = {
                "开始时间": report_info["startTime"],
                "结束时间": report_info["endTime"],
            }
        elif report_type == "month":
            report_info["yearmonth"] = current_time.strftime("%Y-%m")
            extra_details = {"提交月份": report_info["yearmonth"]}

        api_client.submit_report(report_info)

        logger.info(f"{title}已提交")

        return {
            "status": "success",
            "message": f"{title}已提交",
            "task_type": task_name,
            "details": {
                "标题": title,
                "提交时间": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "附件": attachments,
                **extra_details,
            },
            "report_content": content,
        }

    except Exception as e:
        logger.error(f"{task_name}提交失败: {e}")
        return {
            "status": "fail",
            "message": f"{task_name}提交失败: {str(e)}",
            "task_type": task_name,
        }


def submit_daily_report(api_client: ApiClient, config: ConfigManager) -> Dict[str, Any]:
    """提交日报"""
    submit_days = config.get_value("config.reportSettings.daily.submitDays")
    submit_time = config.get_value("config.reportSettings.daily.submitTime")

    def parse_submit_time(value) -> tuple[int, int]:
        if isinstance(value, str) and ":" in value:
            try:
                hh, mm = value.split(":", 1)
                return int(hh), int(mm)
            except Exception:
                return 12, 0
        return 12, 0

    def check_time(t: datetime) -> bool:
        hh, mm = parse_submit_time(submit_time)
        if (t.hour < hh) or (t.hour == hh and t.minute < mm):
            return False
        if submit_days is None:
            return True
        if isinstance(submit_days, list):
            if len(submit_days) == 0:
                return False
            return (t.weekday() + 1) in submit_days
        return True

    return _submit_report_common(
        api_client=api_client,
        config=config,
        report_type="day",
        title_func=lambda c: f"第{c}天日报",
        check_time_func=check_time,
        get_submitted_func=lambda: api_client.get_submitted_reports_info("day"),
        paper_num_key="planInfo.planPaper.dayPaperNum",
        image_count_key="config.reportSettings.daily.imageCount",
        task_name="日报提交",
        form_type=7,
    )


def submit_weekly_report(
    config: ConfigManager, api_client: ApiClient
) -> Dict[str, Any]:
    """提交周报"""
    submit_day = config.get_value("config.reportSettings.weekly.submitTime")
    submit_at = config.get_value("config.reportSettings.weekly.submitAt") or "12:00"

    def parse_submit_time(value) -> tuple[int, int]:
        if isinstance(value, str) and ":" in value:
            try:
                hh, mm = value.split(":", 1)
                return int(hh), int(mm)
            except Exception:
                return 12, 0
        return 12, 0

    def check_time(t: datetime) -> bool:
        hh, mm = parse_submit_time(submit_at)
        if not (t.weekday() + 1 == submit_day):
            return False
        return (t.hour > hh) or (t.hour == hh and t.minute >= mm)

    return _submit_report_common(
        api_client=api_client,
        config=config,
        report_type="week",
        title_func=lambda c: f"第{c}周周报",
        check_time_func=check_time,
        get_submitted_func=lambda: api_client.get_submitted_reports_info("week"),
        paper_num_key="planInfo.planPaper.weekPaperNum",
        image_count_key="config.reportSettings.weekly.imageCount",
        task_name="周报提交",
        form_type=8,
    )


def submit_monthly_report(
    config: ConfigManager, api_client: ApiClient
) -> Dict[str, Any]:
    """提交月报"""
    submit_day = config.get_value("config.reportSettings.monthly.submitTime")
    submit_at = config.get_value("config.reportSettings.monthly.submitAt") or "12:00"
    # 默认每月20号
    if not isinstance(submit_day, int):
        submit_day = 20

    def parse_submit_time(value) -> tuple[int, int]:
        if isinstance(value, str) and ":" in value:
            try:
                hh, mm = value.split(":", 1)
                return int(hh), int(mm)
            except Exception:
                return 12, 0
        return 12, 0

    def check_time(t: datetime) -> bool:
        next_month = t.replace(day=28) + timedelta(days=4)
        last_day_of_month = (next_month - timedelta(days=next_month.day)).day
        target_day = min(submit_day, last_day_of_month)
        if t.day != target_day:
            return False
        hh, mm = parse_submit_time(submit_at)
        return (t.hour > hh) or (t.hour == hh and t.minute >= mm)

    return _submit_report_common(
        api_client=api_client,
        config=config,
        report_type="month",
        title_func=lambda c: f"第{c}月月报",
        check_time_func=check_time,
        get_submitted_func=lambda: api_client.get_submitted_reports_info("month"),
        paper_num_key="planInfo.planPaper.monthPaperNum",
        image_count_key="config.reportSettings.monthly.imageCount",
        task_name="月报提交",
        form_type=9,
    )


def run_task_by_config(
    config_data: Dict[str, Any],
    forced_checkin_type: Optional[str] = None,
    specific_task_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """根据配置字典执行任务"""
    config = ConfigManager(config=config_data)
    
    # 设置日志上下文
    try:
        nickname = desensitize_name(config.get_value("userInfo.nikeName")) or "?"
        _log_ctx.tag = f"{nickname}"
    except Exception:
        _log_ctx.tag = "-"

    results: List[Dict[str, Any]] = []
    pusher = None

    try:
        pusher = MessagePusher(config.get_value("config.pushNotifications"))

        api_client = ApiClient(config)
        if not config.get_value("userInfo.token"):
            api_client.login()

        logger.info("获取用户信息成功")

        if config.get_value("userInfo.userType") == "teacher":
            logger.info("用户身份为教师，跳过计划信息检查")
        elif not config.get_value("planInfo.planId"):
            api_client.fetch_internship_plan()
            logger.info("已获取实习计划信息")

        logger.info(
            f"开始执行：{desensitize_name(config.get_value('userInfo.nikeName'))}"
        )

        all_tasks = [
            ("clock_in", lambda: perform_clock_in(api_client, config, forced_checkin_type)),
            ("daily_report", lambda: submit_daily_report(api_client, config)),
            ("weekly_report", lambda: submit_weekly_report(config, api_client)),
            ("monthly_report", lambda: submit_monthly_report(config, api_client)),
        ]

        results = []
        for t_type, t_func in all_tasks:
            # 如果指定了任务类型，则只执行匹配的任务
            # report 匹配所有报告
            if specific_task_type:
                if specific_task_type == "report" and "report" in t_type:
                    pass
                elif specific_task_type != t_type:
                    continue
            
            results.append(t_func())

    except Exception as e:
        error_message = f"执行任务时发生严重错误: {str(e)}"
        logger.error(error_message)
        results.append(
            {"status": "fail", "message": error_message, "task_type": "系统错误"}
        )
    finally:
        if pusher:
            try:
                pusher.push(results)
            except Exception as e:
                logger.error(f"消息推送失败: {e}")

        logger.info(
            f"执行结束：{desensitize_name(config.get_value('userInfo.nikeName'))}"
        )
        _log_ctx.tag = "-"
        
    return results
