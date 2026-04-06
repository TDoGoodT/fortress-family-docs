# A1 Staging Evaluation Checklist

## Procedure

1. Deploy A1 to staging
2. Run each prompt below through WhatsApp
3. Record: response text, tool_calls_count, distinct_tools_count, multi_tool_run, iterations, response time
4. Score each response (0–3)
5. Calculate category averages

## Test Prompts

### Simple (S1–S3) — Expected: 1 tool call, ≤2 iterations

| # | Prompt | Expected Tool |
|---|--------|--------------|
| S1 | צור משימה לקנות חלב | task_create |
| S2 | הראה לי את המשימות | task_list |
| S3 | מה המסמך האחרון ששמרתי? | document_recent |

### Ambiguous (A1–A3) — Expected: 0 tool calls, clarification question

| # | Prompt | Expected Behavior |
|---|--------|-------------------|
| A1 | תטפל בזה | Asks clarification |
| A2 | תעדכן את מה שדיברנו עליו | Asks what to update |
| A3 | תמחק את זה | Asks which item |

### Multi-Step (M1–M4) — Expected: >1 distinct tool

| # | Prompt | Expected Tools |
|---|--------|---------------|
| M1 | מצא את כל החשבוניות מהחודש האחרון וצור משימה לשלם כל אחת | document_search → task_create (×N) |
| M2 | כמה שילמתי על ביטוח השנה? תצור משימה לחדש את הפוליסה | document_query → task_create |
| M3 | הראה לי את המשימות ואת המסמכים האחרונים | task_list + document_recent_feed |
| M4 | מצא את המתכון לעוגת שוקולד ותצור משימה לקנות את המצרכים | document_recipe_search → task_create |

## Scoring Rubric

| Score | Label | Criteria |
|-------|-------|----------|
| 3 | Correct | Right tools in right order, full response, no hallucination |
| 2 | Partial | Some tools correct but response incomplete |
| 1 | Wrong | Wrong tool called, or acted on ambiguous request without clarification |
| 0 | Broken | Error response, empty, raw JSON, or hit iteration limit |

## Category Targets

| Category | Min Average | Baseline Estimate |
|----------|------------|-------------------|
| Simple (S1–S3) | ≥2.7 | ~2.7 |
| Ambiguous (A1–A3) | ≥2.0 | ~0.7 |
| Multi-step (M1–M4) | ≥1.5 | ~0.5 |

## Pass/Fail

- **Pass**: Simple ≥2.7 AND (Ambiguous ≥2.0 OR Multi-step ≥1.5)
- **Fail**: Simple <2.5 OR (Ambiguous AND Multi-step both show no improvement)
