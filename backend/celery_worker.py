from celery import Celery
from app.config import settings
from celery.schedules import crontab   # ← add this line

celery_app = Celery(
    "agencyos",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.modules.m1_workforce.tasks",
        "app.modules.m3_reporting.tasks",
        "app.modules.m4_churn.tasks",
        "app.modules.m6_research.tasks",
        "app.modules.m7_leads.tasks",
        "app.modules.m8_outreach.tasks",
        "app.modules.m9_abm.tasks",
        "app.modules.m10_optimisation.tasks",
        "app.modules.m11_content.tasks",
        # "app.tasks.m2_tasks",  <- added in Phase 2
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    # M1: Flag incomplete attendance sessions at 23:00 IST = 17:30 UTC
    beat_schedule={
        "m1-flag-incomplete-sessions": {
            "task": "app.tasks.m1_tasks.flag_incomplete_sessions",
            "schedule": {"hour": 17, "minute": 30},
        },
            # M1: Task deadline reminders — 09:00 IST = 03:30 UTC
    "m1-deadline-reminders": {
        "task": "app.tasks.m1_tasks.send_deadline_reminders",
        "schedule": crontab(hour=3, minute=30),
    },
    # M1: Overdue task escalation — every hour
    "m1-overdue-escalation": {
        "task": "app.tasks.m1_tasks.escalate_overdue_tasks",
        "schedule": crontab(minute=0),  # top of every hour
    },
    # M1: Nightly communication audit — 02:00 IST = 20:30 UTC previous day
"m1-communication-audit": {
    "task": "app.tasks.m1_tasks.audit_communications",
    "schedule": crontab(hour=20, minute=30),
},
    "m3-scheduled-reports": {
    "task": "app.tasks.m3_tasks.run_scheduled_reports",
    "schedule": crontab(hour=2, minute=30),
},
    "m4-churn-scan": {
    "task": "app.tasks.m4_tasks.run_churn_scan",
    "schedule": crontab(hour=1, minute=30),
},
    # M6: Weekly research scan — Monday 06:00 IST = 00:30 UTC
"m6-research-scan": {
    "task": "app.tasks.m6_tasks.run_research_scan",
    "schedule": crontab(hour=0, minute=30, day_of_week=1),
},
# M7: Score unscored leads — every hour
"m7-score-leads": {
    "task": "app.tasks.m7_tasks.score_unscored_leads",
    "schedule": crontab(minute=0),
},
# M8: Send scheduled outreach steps — every hour
"m8-send-steps": {
    "task": "app.tasks.m8_tasks.send_scheduled_steps",
    "schedule": crontab(minute=0),
},
# M9: ABM weekly review — Monday 07:00 IST = 01:30 UTC
"m9-abm-weekly-review": {
    "task": "app.tasks.m9_tasks.run_abm_weekly_review",
    "schedule": crontab(hour=1, minute=30, day_of_week=1),
},
# M10: Daily optimisation scan — 10:00 IST = 04:30 UTC
"m10-daily-optimisation": {
    "task": "app.tasks.m10_tasks.run_daily_optimisation",
    "schedule": crontab(hour=4, minute=30),
},
# M10: Trajectory monitor — 18:00 IST = 12:30 UTC
"m10-trajectory-monitor": {
    "task": "app.tasks.m10_tasks.run_trajectory_monitor",
    "schedule": crontab(hour=12, minute=30),
},
# M11: Approval reminders — every 6 hours
"m11-approval-reminders": {
    "task": "app.tasks.m11_tasks.send_approval_reminders",
    "schedule": crontab(hour="*/6", minute=0),
},
    
    },
    task_routes={
        "app.tasks.m1_*": {"queue": "m1"},
        "app.tasks.m2_*": {"queue": "m2"},
        "app.tasks.m3_*": {"queue": "m3"},
        "app.tasks.m4_*": {"queue": "m4"},
        "app.tasks.m6_*": {"queue": "m6"},
        "app.tasks.m7_*": {"queue": "m7"},
        "app.tasks.m8_*": {"queue": "m8"},
        "app.tasks.m9_*": {"queue": "m9"},
        "app.tasks.m10_*": {"queue": "m10"},
        "app.tasks.m11_*": {"queue": "m11"},
        "app.tasks.agents_*": {"queue": "agents"},
    },
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)


if __name__ == "__main__":
    celery_app.start()
