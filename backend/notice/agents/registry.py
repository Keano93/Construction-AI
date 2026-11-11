"""All agents, live and planned. The UI reads this to show what each agent does."""

from ..contract.service import SPEC as CONTRACT_SPEC
from .base import AgentSpec
from .claims_agent.agent import SPEC as CLAIMS_SPEC
from .notice_agent.agent import SPEC as NOTICE_SPEC
from .revision_agent.agent import SPEC as REVISION_SPEC

PLANNED = [
    AgentSpec("valuation_agent", "0.0.0", "Valuation agent", "get_paid",
              "Drafts the monthly payment application from progress evidence and approved variations; chases missing evidence.",
              ["diaries", "programme", "approved variations"], ["draft payment application"], status="planned"),
    AgentSpec("compliance_agent", "0.0.0", "Compliance agent", "get_paid",
              "Tracks RCT, insurance, Safe Pass and RAMS; drafts chasers and sets payment hold for non-compliant subcontractors.",
              ["compliance documents"], ["compliance status", "chase emails", "payment hold"], status="planned"),
    AgentSpec("tender_agent", "0.0.0", "Tender agent", "win_the_work",
              "Summarises a tender pack, builds a risk register of onerous clauses, drafts clarifications and qualifications.",
              ["tender pack"], ["risk register", "clarifications", "qualifications"], status="planned"),
    AgentSpec("bid_levelling_agent", "0.0.0", "Bid levelling agent", "win_the_work",
              "Normalises subcontractor quotes into a like-for-like comparison with exclusions and gaps.",
              ["subcontractor quotes"], ["levelled comparison", "clarifications"], status="planned"),
]

AGENTS: list[AgentSpec] = [NOTICE_SPEC, REVISION_SPEC, CLAIMS_SPEC, CONTRACT_SPEC, *PLANNED]
