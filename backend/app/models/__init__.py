from app.models.base import Base, TimestampMixin, UUIDMixin


def import_all_models() -> None:
    """Import all ORM models so SQLAlchemy metadata is fully registered."""

    from app.modules.m10_optimisation.models import (  # noqa: F401
        OptimisationConfig,
        OptimisationRecommendation,
        OptimisationRun,
        PredictiveAlert,
    )
    from app.modules.m11_content.models import (  # noqa: F401
        ClientApprovalRequest,
        ContentBrief,
        ContentDraft,
    )
    from app.modules.m1_workforce.models_attendance import (  # noqa: F401
        AttendanceSession,
        GeofenceZone,
    )
    from app.modules.m1_workforce.models_communication import CommunicationLog  # noqa: F401
    from app.modules.m1_workforce.models_payroll import Payslip, PayrollRun  # noqa: F401
    from app.modules.m1_workforce.models_task import Task, TaskStatusHistory  # noqa: F401
    from app.modules.m2_operations.models import Invoice, OnboardingFlow, OnboardingStep  # noqa: F401
    from app.modules.m3_reporting.models import ClientReportConfig, Report  # noqa: F401
    from app.modules.m4_churn.models import ChurnAlert  # noqa: F401
    from app.modules.m5_campaigns.models import Campaign, CampaignTask  # noqa: F401
    from app.modules.m6_research.models import ResearchBrief, TrackedCompetitor  # noqa: F401
    from app.modules.m7_leads.models import IcpProfile, Lead, LeadScore  # noqa: F401
    from app.modules.m8_outreach.models import OutreachSequence, OutreachStep  # noqa: F401
    from app.modules.m9_abm.models import AbmAccount, AbmAccountNote, AbmTouch  # noqa: F401
    from app.modules.people_and_tenant.agencies.models import Agency, AgencyModule  # noqa: F401
    from app.modules.people_and_tenant.users.models import Client, Employee, User  # noqa: F401


__all__ = ["Base", "TimestampMixin", "UUIDMixin", "import_all_models"]
