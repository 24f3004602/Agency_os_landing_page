from fastapi import APIRouter

from app.modules.people_and_tenant.auth.api import router as auth_router
from app.modules.m1_workforce.attendance_api import router as attendance_router
from app.modules.m1_workforce.geofence_api import router as geofence_router
from app.modules.m1_workforce.tasks_api import router as tasks_router
from app.modules.people_and_tenant.employees.api import router as employees_router
from app.modules.people_and_tenant.clients.api import router as clients_router
from app.modules.people_and_tenant.agencies.superadmin_api import router as superadmin_router
from app.modules.m1_workforce.payroll_api import router as payroll_router
from app.modules.m1_workforce.communications_api import router as communications_router
from app.modules.m2_operations.api import router as operations_router
from app.modules.m3_reporting.api import router as reporting_router
from app.modules.m4_churn.api import router as churn_router
from app.modules.m5_campaigns.api import router as campaigns_router
from app.modules.m6_research.api import router as research_router
from app.modules.m7_leads.api import router as leads_router
from app.modules.m8_outreach.api import router as outreach_router
from app.modules.m9_abm.api import router as abm_router
from app.modules.m10_optimisation.api import router as optimisation_router
from app.modules.m11_content.api import router as content_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(attendance_router)   
api_router.include_router(geofence_router)     
api_router.include_router(tasks_router)    
api_router.include_router(employees_router)   
api_router.include_router(clients_router)  

api_router.include_router(superadmin_router) 

api_router.include_router(payroll_router)    

api_router.include_router(communications_router)     

api_router.include_router(operations_router)                    

api_router.include_router(reporting_router)  

api_router.include_router(churn_router)                

api_router.include_router(campaigns_router)                    

api_router.include_router(research_router)        

api_router.include_router(leads_router)                

api_router.include_router(outreach_router)    

api_router.include_router(abm_router)              # ← ADD 

api_router.include_router(optimisation_router)      

api_router.include_router(content_router)                  # ← ADD         
# Future module routers added below:
# api_router.include_router(tasks_router)      # M1 Phase 2
# api_router.include_router(payroll_router)    # M1 Phase 3
# api_router.include_router(employees_router)
# api_router.include_router(clients_router)
# api_router.include_router(agencies_router)   <- superadmin
