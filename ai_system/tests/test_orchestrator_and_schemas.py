from __future__ import annotations

from ai_system.langgraph import nodes
from ai_system.app import orchestrator
from ai_system.app.schemas import PortfolioReviewRequest


def test_portfolio_review_invokes_graph_with_payload_and_mode(monkeypatch):
    captured: dict = {}

    class FakeGraph:
        def invoke(self, state):
            captured["state"] = state
            return {
                "response": {
                    "portfolio_id": state["portfolio"]["id"],
                    "langgraph_route": state["route"],
                    "crew_output": "ok",
                }
            }

    monkeypatch.setattr(orchestrator, "graph", FakeGraph())

    result = orchestrator.portfolio_review(
        {"id": 42, "name": "Demo"},
        [{"symbol": "AAPL", "type": "buy"}],
        mode="full",
    )

    assert result == {
        "portfolio_id": 42,
        "langgraph_route": "full",
        "crew_output": "ok",
    }
    assert captured["state"]["portfolio"] == {"id": 42, "name": "Demo"}
    assert captured["state"]["transactions"] == [{"symbol": "AAPL", "type": "buy"}]
    assert captured["state"]["route"] == "full"
    assert "request_id" in captured["state"]


def test_comprehensive_portfolio_review_uses_full_mode(monkeypatch):
    captured: dict = {}

    def fake_portfolio_review(portfolio_payload, transactions_payload, mode="quick"):
        captured["mode"] = mode
        return {"mode": mode}

    monkeypatch.setattr(orchestrator, "portfolio_review", fake_portfolio_review)

    assert orchestrator.comprehensive_portfolio_review({}, []) == {"mode": "full"}
    assert captured["mode"] == "full"


def test_crew_two_market_summary_uses_structured_output(monkeypatch):
    monkeypatch.setattr(
        nodes.portfolio,
        "analyze_portfolio",
        lambda portfolio: {"analysis": "Portfolio analysis ok."},
    )
    monkeypatch.setattr(nodes, "_emit_llm_thinking", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        nodes.market,
        "analyze_sentiment",
        lambda symbols, detail_level: {
            "structured_output": {
                "summary": "MSFT and NVDA signals are mixed.",
                "severity": "medium",
                "confidence": "high",
                "key_factors": ["Earnings and AI demand are the main driver."],
                "recommended_actions": ["Validate with live prices before trading."],
            }
        },
    )
    monkeypatch.setattr(
        nodes.customer_context,
        "build_customer_profile",
        lambda customer_id, profile_data: {
            "structured_output": {
                "summary": "Behavior matches the known customer profile.",
                "severity": "low",
                "confidence": "high",
                "key_factors": ["Profile richness: high"],
                "recommended_actions": ["Use the profile for routine context enrichment."],
            },
            "consistency_score": 82,
            "consistency_label": "consistent",
        },
    )
    state = {
        "portfolio": {
            "id": 1,
            "name": "Demo",
            "assets": [{"symbol": "MSFT"}, {"symbol": "NVDA"}],
        },
        "transactions": [],
        "analysis_trace": [],
    }

    result = nodes.run_full_crew_two(state)

    assert "Market MSFT and NVDA signals are mixed." in result["crew2_output"]
    assert (
        "Signal: severity=medium; confidence=high; "
        "driver=Earnings and AI demand are the main driver."
    ) in result["crew2_output"]
    assert "Action: Validate with live prices before trading." in result["crew2_output"]
    assert "consistency=82/100 (consistent)" in result["crew2_output"]
    assert result["crew2_results"]["portfolio_analysis"]["analysis"] == "Portfolio analysis ok."
    assert result["crew2_results"]["customer_context"]["consistency_label"] == "consistent"
    assert "neutral bias" not in result["crew2_output"]


def test_crew_one_uses_compliance_agent(monkeypatch):
    compliance_called: dict = {}
    risk_called: dict = {}

    monkeypatch.setattr(nodes.risk, "score_transaction", lambda txn: {"score": 12})
    monkeypatch.setattr(
        nodes.risk,
        "assess_portfolio_risk",
        lambda portfolio, market_conditions, customer_context=None: risk_called.update(
            {
                "portfolio": portfolio,
                "market_conditions": market_conditions,
                "customer_context": customer_context,
            }
        )
        or {"agent": "RiskAssessment", "timestamp": "now", "structured_output": {"summary": "ok", "severity": "low", "confidence": "medium", "key_factors": ["x"], "recommended_actions": ["y"], "follow_up": ["z"], "raw_text": "ok"}, "risk_analysis": "Risk analysis ok."},
    )
    monkeypatch.setattr(
        nodes.risk,
        "detect_fraud_risk",
        lambda transactions, portfolio, ml_scores: {
            "agent": "RiskDetector",
            "timestamp": "now",
            "structured_output": {
                "summary": "Fraud review ok.",
                "severity": "low",
                "confidence": "medium",
                "key_factors": ["none"],
                "recommended_actions": ["monitor"],
                "follow_up": ["none"],
                "raw_text": "Fraud review ok.",
            },
            "assessment": "Fraud review ok.",
        },
    )
    monkeypatch.setattr(nodes, "_emit_llm_thinking", lambda *args, **kwargs: None)

    def fake_compliance_invoke(portfolio, transactions, mode="quick", customer_context=None):
        compliance_called["portfolio"] = portfolio
        compliance_called["transactions"] = transactions
        compliance_called["mode"] = mode
        compliance_called["customer_context"] = customer_context
        return {
            "agent": "compliance",
            "timestamp": "now",
            "prechecks": {
                "rule_hits": [
                    {
                        "rule_id": "UNSUPPORTED_TXN_TYPE",
                        "severity": "high",
                        "basis": "internal_schema_control",
                        "description": "Unsupported transaction type found.",
                    }
                ]
            },
            "summary": "Fallback compliance summary.",
            "structured_output": {
                "summary": "Compliance agent reviewed transaction policy checks.",
                "severity": "high",
                "confidence": "medium",
                "key_factors": ["Unsupported transaction type found."],
                "recommended_actions": ["Queue the activity for analyst review."],
            },
        }

    monkeypatch.setattr(nodes.compliance, "invoke", fake_compliance_invoke)
    state = {
        "portfolio": {"id": 1, "name": "Demo"},
        "transactions": [{"symbol": "MSFT", "type": "buy"}],
        "customer_context_seed": {
            "customer_id": "customer-1",
            "profile_data": {"segment": "premium", "risk_profile": "moderate"},
        },
        "analysis_trace": [],
    }

    result = nodes.run_full_crew_one(state)

    assert risk_called["customer_context"] == {
        "segment": "premium",
        "risk_profile": "moderate",
    }
    assert compliance_called == {
        "portfolio": {"id": 1, "name": "Demo"},
        "transactions": [{"symbol": "MSFT", "type": "buy"}],
        "mode": "full",
        "customer_context": {
            "segment": "premium",
            "risk_profile": "moderate",
        },
    }
    assert "Compliance 1 compliance precheck(s) require analyst review." in result["crew1_output"]
    assert (
        "Signal: severity=high; confidence=medium; "
        "basis=internal_schema_control; driver=Unsupported transaction type found."
    ) in result["crew1_output"]
    assert "Action: Queue the activity for analyst review." in result["crew1_output"]
    assert result["crew1_results"]["risk_assessment"]["risk_analysis"] == "Risk analysis ok."
    assert result["crew1_results"]["risk_detection"]["assessment"] == "Fraud review ok."
    assert result["crew1_results"]["compliance"]["structured_output"]["severity"] == "high"


def test_ingest_request_prepares_customer_context_seed():
    state = nodes.ingest_request(
        {
            "portfolio": {
                "id": 7,
                "name": "Demo Portfolio",
                "total_value": 120000,
                "cash_balance": 3000,
                "assets": [{"symbol": "MSFT"}, {"symbol": "NVDA"}],
            },
            "transactions": [
                {"symbol": "MSFT", "type": "buy", "quantity": 10, "price": 500},
                {"symbol": "MSFT", "type": "buy", "quantity": 15, "price": 600},
            ],
        }
    )

    assert state["customer_context_seed"]["customer_id"] == "7"
    assert state["customer_context_seed"]["profile_data"]["segment"] == "affluent"
    assert state["customer_context_seed"]["profile_data"]["transaction_count"] == 2


def test_full_run_sequences_real_crew_dependencies(monkeypatch):
    call_order: list[str] = []

    def fake_crew_one(state):
        call_order.append("crew1")
        state["crew1_output"] = "crew1 complete"
        state["crew1_results"] = {"risk_assessment": {"structured_output": {"summary": "risk"}}}
        state["analysis_trace"] = state.get("analysis_trace", [])
        return state

    def fake_crew_two(state):
        call_order.append("crew2")
        assert state["crew1_output"] == "crew1 complete"
        state["crew2_output"] = "crew2 complete"
        state["crew2_results"] = {"customer_context": {"structured_output": {"summary": "customer"}}}
        return state

    def fake_crew_three(state):
        call_order.append("crew3")
        assert state["crew1_output"] == "crew1 complete"
        assert state["crew2_output"] == "crew2 complete"
        state["crew3_output"] = "crew3 complete"
        state["crews_run"] = 3
        return state

    monkeypatch.setattr(nodes, "run_full_crew_one", fake_crew_one)
    monkeypatch.setattr(nodes, "run_full_crew_two", fake_crew_two)
    monkeypatch.setattr(nodes, "run_full_crew_three", fake_crew_three)

    result = nodes.run_full_crews_parallel({"analysis_trace": [], "errors": []})

    assert call_order == ["crew1", "crew2", "crew3"]
    assert result["crew3_output"] == "crew3 complete"


def test_crew_three_uses_alert_and_escalation_agents(monkeypatch):
    monkeypatch.setattr(
        nodes.alert_intake,
        "process_accumulated_findings",
        lambda findings: {
            "structured_output": {
                "summary": "Escalate for human review.",
                "severity": "high",
                "confidence": "high",
                "key_factors": ["elevated_ml_risk"],
                "recommended_actions": ["Prioritize for analyst review."],
            },
            "escalation_recommendation": "Yes",
            "urgency_level": "High",
            "priority_tier": "P2",
        },
    )
    monkeypatch.setattr(
        nodes.explanation,
        "summarize_analysis",
        lambda analysis_results, detail_level: {
            "summary": "Explanation summary ok.",
            "structured_output": {"summary": "Explanation summary ok."},
        },
    )
    monkeypatch.setattr(
        nodes.escalation,
        "evaluate_escalation_need",
        lambda incident, severity_factors: {
            "structured_output": {
                "summary": "Escalation review says specialist handling is required.",
                "severity": "critical",
                "confidence": "medium",
                "key_factors": ["Regulatory markers: aml, sar"],
                "recommended_actions": ["Escalate immediately."],
            },
            "action_recommendation": "Report",
            "priority_tier": "P1",
            "evidence_portfolio": ["Risk score: 88", "Regulatory markers: aml, sar"],
        },
    )
    monkeypatch.setattr(
        nodes.escalation,
        "generate_case_summary",
        lambda case_data, interactions, decisions: {
            "summary": "Final case summary ready for handoff.",
            "structured_output": {
                "summary": "Final case summary ready for handoff.",
                "severity": "critical",
                "confidence": "medium",
                "key_factors": ["Risk score: 88"],
                "recommended_actions": ["Escalate immediately."],
            },
        },
    )
    monkeypatch.setattr(nodes, "_emit_llm_thinking", lambda *args, **kwargs: None)

    state = {
        "request_id": "2026-05-06T00:00:00+00:00",
        "portfolio": {"id": 7, "name": "Demo", "total_value": 90000},
        "transactions": [],
        "ml_summary": "High/Critical: 1",
        "crew1_output": "Risk output",
        "crew1_results": {
            "ml_scores": [{"risk_score": 88, "risk_label": "critical", "hard_block": False}],
            "compliance": {"prechecks": {"rule_hits": [{"rule_id": "AML_ALERT", "description": "AML review"}]}},
        },
        "crew2_output": "Portfolio output",
        "crew2_results": {
            "customer_context": {
                "structured_output": {"summary": "Behavior matches profile."},
                "consistency_label": "consistent",
            },
            "portfolio_analysis": {"structured_output": {"summary": "Portfolio summary."}},
            "market_intelligence": {"structured_output": {"summary": "Market summary."}},
        },
        "analysis_trace": [],
    }

    result = nodes.run_full_crew_three(state)

    assert "priority=P2" in result["crew3_output"]
    assert "action=Report" in result["crew3_output"]
    assert "Final case summary ready for handoff." in result["crew3_output"]
    assert result["crew3_results"]["alert_intake"]["priority_tier"] == "P2"
    assert result["crew3_results"]["escalation_evaluation"]["action_recommendation"] == "Report"
    assert result["crew3_results"]["explanation"]["summary"] == "Explanation summary ok."


def test_crew_three_passes_structured_evidence_to_explanation(monkeypatch):
    captured: dict = {}

    monkeypatch.setattr(
        nodes.alert_intake,
        "process_accumulated_findings",
        lambda findings: {
            "structured_output": {
                "summary": "Alert summary.",
                "severity": "high",
                "confidence": "high",
                "key_factors": ["critical_upstream_signal"],
                "recommended_actions": ["Escalate."],
            },
            "escalation_recommendation": "Yes",
            "urgency_level": "High",
            "priority_tier": "P2",
        },
    )

    def fake_summarize_analysis(analysis_results, detail_level):
        captured["analysis_results"] = analysis_results
        captured["detail_level"] = detail_level
        return {
            "summary": "Explanation summary ok.",
            "structured_output": {"summary": "Explanation summary ok."},
        }

    monkeypatch.setattr(nodes.explanation, "summarize_analysis", fake_summarize_analysis)
    monkeypatch.setattr(
        nodes.escalation,
        "evaluate_escalation_need",
        lambda incident, severity_factors: {
            "structured_output": {
                "summary": "Escalation review.",
                "severity": "high",
                "confidence": "medium",
                "key_factors": ["Risk score: 77"],
                "recommended_actions": ["Escalate."],
            },
            "action_recommendation": "Escalate",
            "priority_tier": "P2",
            "evidence_portfolio": ["Risk score: 77"],
        },
    )
    monkeypatch.setattr(
        nodes.escalation,
        "generate_case_summary",
        lambda case_data, interactions, decisions: {
            "summary": "Case summary.",
            "structured_output": {
                "summary": "Case summary.",
                "severity": "high",
                "confidence": "medium",
                "key_factors": ["Risk score: 77"],
                "recommended_actions": ["Escalate."],
            },
        },
    )
    monkeypatch.setattr(nodes, "_emit_llm_thinking", lambda *args, **kwargs: None)

    nodes.run_full_crew_three(
        {
            "request_id": "2026-05-06T00:00:00+00:00",
            "portfolio": {"id": 9, "name": "Demo", "total_value": 50000},
            "ml_summary": "High/Critical: 1",
            "crew1_output": "Crew 1 summary",
            "crew1_results": {
                "ml_scores": [{"risk_score": 77, "risk_label": "high", "hard_block": False}],
                "risk_assessment": {
                    "structured_output": {
                        "summary": "Risk assessment summary.",
                        "severity": "high",
                        "confidence": "medium",
                        "key_factors": ["Liquidity concentration"],
                        "recommended_actions": ["Review concentration."],
                        "follow_up": ["Monitor."],
                        "raw_text": "Risk assessment summary.",
                    }
                },
                "risk_detection": {
                    "structured_output": {
                        "summary": "Fraud detection summary.",
                        "severity": "medium",
                        "confidence": "medium",
                        "key_factors": ["Velocity spike"],
                        "recommended_actions": ["Review activity."],
                        "follow_up": ["Monitor."],
                        "raw_text": "Fraud detection summary.",
                    }
                },
                "compliance": {
                    "prechecks": {"rule_hits": []},
                    "structured_output": {
                        "summary": "Compliance summary.",
                        "severity": "low",
                        "confidence": "high",
                        "key_factors": ["No major policy breach"],
                        "recommended_actions": ["Continue monitoring."],
                        "follow_up": ["Document."],
                        "raw_text": "Compliance summary.",
                    }
                },
            },
            "crew2_output": "Crew 2 summary",
            "crew2_results": {
                "portfolio_analysis": {
                    "structured_output": {
                        "summary": "Portfolio analysis summary.",
                        "severity": "medium",
                        "confidence": "medium",
                        "key_factors": ["Thin diversification"],
                        "recommended_actions": ["Rebalance."],
                        "follow_up": ["Monitor."],
                        "raw_text": "Portfolio analysis summary.",
                    }
                },
                "market_intelligence": {
                    "structured_output": {
                        "summary": "Market summary.",
                        "severity": "medium",
                        "confidence": "medium",
                        "key_factors": ["Macro uncertainty"],
                        "recommended_actions": ["Validate live data."],
                        "follow_up": ["Monitor."],
                        "raw_text": "Market summary.",
                    }
                },
                "customer_context": {
                    "consistency_label": "review",
                    "structured_output": {
                        "summary": "Customer context summary.",
                        "severity": "medium",
                        "confidence": "high",
                        "key_factors": ["Behavior drift"],
                        "recommended_actions": ["Review profile."],
                        "follow_up": ["Refresh KYC."],
                        "raw_text": "Customer context summary.",
                    }
                },
            },
            "analysis_trace": [],
        }
    )

    assert captured["detail_level"] == "medium"
    assert captured["analysis_results"]["risk_assessment"]["summary"] == "Risk assessment summary."
    assert captured["analysis_results"]["customer_context"]["summary"] == "Customer context summary."
    assert captured["analysis_results"]["alert_intake"]["summary"] == "Alert summary."


def test_crew_three_passes_structured_dossier_to_escalation(monkeypatch):
    captured: dict = {}

    monkeypatch.setattr(
        nodes.alert_intake,
        "process_accumulated_findings",
        lambda findings: {
            "structured_output": {
                "summary": "Alert summary.",
                "severity": "high",
                "confidence": "high",
                "key_factors": ["critical_upstream_signal"],
                "recommended_actions": ["Escalate."],
            },
            "escalation_recommendation": "Yes",
            "urgency_level": "High",
            "priority_tier": "P2",
        },
    )
    monkeypatch.setattr(
        nodes.explanation,
        "summarize_analysis",
        lambda analysis_results, detail_level: {
            "summary": "Explanation summary.",
            "structured_output": {
                "summary": "Explanation summary.",
                "severity": "high",
                "confidence": "medium",
                "key_factors": ["Liquidity concentration"],
                "recommended_actions": ["Escalate."],
                "follow_up": ["Monitor."],
                "raw_text": "Explanation summary.",
            },
        },
    )

    def fake_evaluate_escalation_need(incident, severity_factors):
        captured["incident"] = incident
        captured["severity_factors"] = severity_factors
        return {
            "structured_output": {
                "summary": "Escalation review.",
                "severity": "high",
                "confidence": "medium",
                "key_factors": ["Risk score: 77"],
                "recommended_actions": ["Escalate."],
            },
            "action_recommendation": "Escalate",
            "priority_tier": "P2",
            "evidence_portfolio": ["Risk score: 77"],
        }

    def fake_generate_case_summary(case_data, interactions, decisions):
        captured["case_data"] = case_data
        captured["interactions"] = interactions
        captured["decisions"] = decisions
        return {
            "summary": "Case summary.",
            "structured_output": {
                "summary": "Case summary.",
                "severity": "high",
                "confidence": "medium",
                "key_factors": ["Risk score: 77"],
                "recommended_actions": ["Escalate."],
            },
        }

    monkeypatch.setattr(
        nodes.escalation, "evaluate_escalation_need", fake_evaluate_escalation_need
    )
    monkeypatch.setattr(
        nodes.escalation, "generate_case_summary", fake_generate_case_summary
    )
    monkeypatch.setattr(nodes, "_emit_llm_thinking", lambda *args, **kwargs: None)

    nodes.run_full_crew_three(
        {
            "request_id": "2026-05-06T00:00:00+00:00",
            "portfolio": {"id": 9, "name": "Demo", "total_value": 50000},
            "ml_summary": "High/Critical: 1",
            "crew1_output": "Crew 1 summary",
            "crew1_results": {
                "ml_scores": [{"risk_score": 77, "risk_label": "high", "hard_block": False}],
                "risk_assessment": {
                    "structured_output": {
                        "summary": "Risk assessment summary.",
                        "severity": "high",
                        "confidence": "medium",
                        "key_factors": ["Liquidity concentration"],
                        "recommended_actions": ["Review concentration."],
                        "follow_up": ["Monitor."],
                        "raw_text": "Risk assessment summary.",
                    }
                },
                "risk_detection": {
                    "structured_output": {
                        "summary": "Fraud detection summary.",
                        "severity": "medium",
                        "confidence": "medium",
                        "key_factors": ["Velocity spike"],
                        "recommended_actions": ["Review activity."],
                        "follow_up": ["Monitor."],
                        "raw_text": "Fraud detection summary.",
                    }
                },
                "compliance": {
                    "prechecks": {
                        "rule_hits": [{"rule_id": "AML_ALERT", "description": "AML review"}]
                    },
                    "structured_output": {
                        "summary": "Compliance summary.",
                        "severity": "high",
                        "confidence": "high",
                        "key_factors": ["AML review"],
                        "recommended_actions": ["Escalate."],
                        "follow_up": ["Document."],
                        "raw_text": "Compliance summary.",
                    }
                },
            },
            "crew2_output": "Crew 2 summary",
            "crew2_results": {
                "portfolio_analysis": {
                    "structured_output": {
                        "summary": "Portfolio analysis summary.",
                        "severity": "medium",
                        "confidence": "medium",
                        "key_factors": ["Thin diversification"],
                        "recommended_actions": ["Rebalance."],
                        "follow_up": ["Monitor."],
                        "raw_text": "Portfolio analysis summary.",
                    }
                },
                "market_intelligence": {
                    "structured_output": {
                        "summary": "Market summary.",
                        "severity": "medium",
                        "confidence": "medium",
                        "key_factors": ["Macro uncertainty"],
                        "recommended_actions": ["Validate live data."],
                        "follow_up": ["Monitor."],
                        "raw_text": "Market summary.",
                    }
                },
                "customer_context": {
                    "consistency_label": "review",
                    "structured_output": {
                        "summary": "Customer context summary.",
                        "severity": "medium",
                        "confidence": "high",
                        "key_factors": ["Behavior drift"],
                        "recommended_actions": ["Review profile."],
                        "follow_up": ["Refresh KYC."],
                        "raw_text": "Customer context summary.",
                    }
                },
            },
            "analysis_trace": [],
        }
    )

    assert captured["incident"]["alert_intake"]["summary"] == "Alert summary."
    assert captured["severity_factors"]["risk_assessment"]["summary"] == "Risk assessment summary."
    assert captured["severity_factors"]["customer_context"]["summary"] == "Customer context summary."
    assert captured["interactions"][0]["agent"] == "risk_assessment"
    assert captured["interactions"][2]["rule_hits"][0]["rule_id"] == "AML_ALERT"
    assert captured["decisions"][0]["agent"] == "alert_intake"
    assert captured["decisions"][1]["agent"] == "explanation"


def test_portfolio_review_request_defaults_and_nested_dump():
    request = PortfolioReviewRequest(
        portfolio={
            "id": 1,
            "name": "Test Portfolio",
            "assets": [{"symbol": "AAPL", "quantity": 2, "current_price": 200}],
        }
    )

    assert request.mode == "quick"
    assert request.transactions == []
    assert request.portfolio.total_value == 0
    assert request.portfolio.assets[0].symbol == "AAPL"
    assert request.portfolio.model_dump()["assets"][0]["current_price"] == 200.0
