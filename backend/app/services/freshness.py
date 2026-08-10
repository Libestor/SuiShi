from datetime import datetime, timezone


def freshness_label(updated_at: datetime) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    seconds = max(0, int((now - updated_at).total_seconds()))
    hours = seconds // 3600
    if hours < 2:
        return "刚刚更新", hours
    if hours < 24:
        return f"{hours} 小时前", hours
    days = hours // 24
    return f"{days} 天前", hours
