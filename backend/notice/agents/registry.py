"""All agents, live and planned. The UI reads this to show what each agent does."""

from ..contract.service import SPEC as CONTRACT_SPEC
from .base import AgentSpec
from .notice_agent.agent import SPEC as NOTICE_SPEC

PLANNED = [
    AgentSpec("revision_agent", "0.0.0", "Revision agent", "protect_the_money",
              "Compares two revisions of a drawing register, spec or drawing; lists changes, likely cost impact, and hands potential variations to the Notice agent.",
              ["drawing register", "spec", "drawing PDF"], ["change list", "potential variation"], status="planned"),
    AgentSpec("claims_agent", "0.0.0", "Claims agent", "protect_the_money",
              "Assembles a chronological evidence timeline for selected events and drafts a claim narrative.",
              ["events", "project record"], ["timeline", "claim narrative"], status="planned"),
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

AGENTS: list[AgentSpec] = [NOTICE_SPEC, CONTRACT_SPEC, *PLANNED]
