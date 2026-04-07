"""Fortress — Bedrock cost query tool.

Queries AWS Cost Explorer for current-month Amazon Bedrock spending
and returns a Hebrew-formatted summary.
"""
from __future__ import annotations

import logging
from datetime import date

from src.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    _HAS_BOTO3 = True
except ImportError:
    _HAS_BOTO3 = False


def query_bedrock_cost() -> str:
    """Query AWS Cost Explorer for current month Bedrock spending.

    Returns a Hebrew-formatted string with total cost, service breakdown,
    and date range.  Uses sync boto3 — caller is responsible for threading
    if needed.
    """
    if not _HAS_BOTO3:
        return "שירות שאילתת עלויות לא זמין — boto3 לא מותקן"

    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        return "הרשאות שאילתת עלויות לא מוגדרות. נדרשת הרשאת ce:GetCostAndUsage"

    today = date.today()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()

    # Cost Explorer requires start < end; if today is the 1st, range is empty
    if start == end:
        return "לא נמצאו נתוני עלויות לחודש הנוכחי"

    try:
        ce = boto3.client(
            "ce",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )

        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            Filter={
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": ["Amazon Bedrock"],
                }
            },
            GroupBy=[
                {"Type": "DIMENSION", "Key": "SERVICE"},
            ],
        )
    except NoCredentialsError:
        return "הרשאות שאילתת עלויות לא מוגדרות. נדרשת הרשאת ce:GetCostAndUsage"
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "AccessDeniedException":
            return "אין הרשאה לשאילתת עלויות. נדרשת הרשאת ce:GetCostAndUsage ב-IAM"
        logger.error("cost_tool: Cost Explorer API error: %s", exc)
        return "לא הצלחתי לשלוף נתוני עלויות"
    except Exception as exc:
        logger.error("cost_tool: unexpected error: %s", exc)
        return "לא הצלחתי לשלוף נתוני עלויות"

    results = resp.get("ResultsByTime", [])
    if not results:
        return "לא נמצאו נתוני עלויות לחודש הנוכחי"

    # Collect service breakdown from groups
    groups = results[0].get("Groups", [])
    if not groups:
        # No grouped data — check Total fallback
        total_block = results[0].get("Total", {}).get("UnblendedCost", {})
        amount = total_block.get("Amount", "0")
        if float(amount) == 0:
            return "לא נמצאו נתוני עלויות לחודש הנוכחי"
        currency = total_block.get("Unit", "USD")
        return (
            f"💰 עלויות Amazon Bedrock לחודש הנוכחי:\n"
            f"סה\"כ: {float(amount):.2f} {currency}\n"
            f"תקופה: {start} עד {end}"
        )

    # Sum total and build per-service breakdown
    total_amount = 0.0
    currency = "USD"
    breakdown_lines: list[str] = []
    for group in groups:
        svc_name = group.get("Keys", [""])[0]
        metrics = group.get("Metrics", {}).get("UnblendedCost", {})
        amt = float(metrics.get("Amount", "0"))
        currency = metrics.get("Unit", "USD")
        total_amount += amt
        if amt > 0:
            breakdown_lines.append(f"  • {svc_name}: {amt:.2f} {currency}")

    if total_amount == 0:
        return "לא נמצאו נתוני עלויות לחודש הנוכחי"

    msg = f"💰 עלויות Amazon Bedrock לחודש הנוכחי:\n"
    msg += f"סה\"כ: {total_amount:.2f} {currency}\n"
    if breakdown_lines:
        msg += "פירוט:\n" + "\n".join(breakdown_lines) + "\n"
    msg += f"תקופה: {start} עד {end}"
    return msg
