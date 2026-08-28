from __future__ import annotations

from dataclasses import dataclass, field


VALID_DAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def time_to_minutes(value: str) -> int:
    try:
        parts = value.split(":")
        if len(parts) != 2 or any(len(part) != 2 for part in parts):
            raise ValueError
        hour, minute = map(int, parts)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Time must be a valid 24-hour HH:MM value.") from exc
    if hour not in range(24) or minute not in range(60):
        raise ValueError("Time must be a valid 24-hour HH:MM value.")
    return hour * 60 + minute


def minutes_to_time(value: int) -> str:
    if value not in range(24 * 60):
        raise ValueError("Minute value must fall within a single day.")
    return f"{value // 60:02d}:{value % 60:02d}"


INSTITUTIONAL_POLICY_VERSION = "semester-parity-v1"


def parse_semester_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    else:
        text = str(value or "").strip()
        if not text.isdigit():
            return None
        number = int(text)
    return number if 1 <= number <= 8 else None


def allowed_days_for(
    semester: object,
    class_type: str,
) -> tuple[str, ...]:
    semester_number = parse_semester_number(semester)
    if semester_number is None:
        raise ValueError("Semester must be an integer from 1 through 8.")
    kind = str(class_type or "").strip().lower()
    if kind not in {"lecture", "lab"}:
        raise ValueError("class_type must be lecture or lab.")

    if semester_number % 2:
        return (
            ("Monday", "Wednesday")
            if kind == "lecture"
            else ("Thursday",)
        )
    return (
        ("Tuesday", "Thursday")
        if kind == "lecture"
        else ("Friday",)
    )


@dataclass(frozen=True)
class BlockedPeriod:
    day: str
    start_time: str
    end_time: str
    reason: str

    def __post_init__(self) -> None:
        if self.day not in VALID_DAYS:
            raise ValueError("Blocked-period day is invalid.")
        if time_to_minutes(self.start_time) >= time_to_minutes(self.end_time):
            raise ValueError("Blocked period end must be after its start.")


@dataclass(frozen=True)
class SchedulingPolicy:
    operating_days: tuple[str, ...] = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    )
    opens_at: str = "08:00"
    closes_at: str = "20:00"
    slot_interval_minutes: int = 30
    blocked_periods: tuple[BlockedPeriod, ...] = field(default_factory=tuple)
    minimum_duration_minutes: int = 30
    maximum_duration_minutes: int = 240
    maximum_candidates_per_entry: int = 250

    def __post_init__(self) -> None:
        if not self.operating_days or any(day not in VALID_DAYS for day in self.operating_days):
            raise ValueError("Policy operating days must be valid and non-empty.")
        if len(set(self.operating_days)) != len(self.operating_days):
            raise ValueError("Policy operating days must not contain duplicates.")
        if time_to_minutes(self.opens_at) >= time_to_minutes(self.closes_at):
            raise ValueError("Policy closing time must be after opening time.")
        if self.slot_interval_minutes < 5 or self.slot_interval_minutes > 120:
            raise ValueError("Policy slot interval must be between 5 and 120 minutes.")
        if self.minimum_duration_minutes < 1:
            raise ValueError("Policy minimum duration must be positive.")
        if self.maximum_duration_minutes < self.minimum_duration_minutes:
            raise ValueError("Policy maximum duration must not be below the minimum.")
        if self.maximum_candidates_per_entry < 1:
            raise ValueError("Policy candidate limit must be positive.")
        if any(period.day not in self.operating_days for period in self.blocked_periods):
            raise ValueError("Blocked periods must fall on configured operating days.")

    def validate_slot(
        self,
        *,
        day: str,
        start_time: str,
        end_time: str,
    ) -> list[str]:
        failures: list[str] = []
        if day not in self.operating_days:
            failures.append(f"{day} is outside configured operating days.")
        start = time_to_minutes(start_time)
        end = time_to_minutes(end_time)
        duration = end - start
        if start < time_to_minutes(self.opens_at) or end > time_to_minutes(self.closes_at):
            failures.append(
                f"Slot is outside configured operating hours {self.opens_at}-{self.closes_at}."
            )
        if duration < self.minimum_duration_minutes or duration > self.maximum_duration_minutes:
            failures.append(
                "Class duration is outside the configured institutional duration range."
            )
        for blocked in self.blocked_periods:
            if blocked.day != day:
                continue
            if start < time_to_minutes(blocked.end_time) and time_to_minutes(blocked.start_time) < end:
                failures.append(f"Slot overlaps blocked period: {blocked.reason}.")
        return failures

    def generate_slots(
        self,
        *,
        duration_minutes: int,
        include_blocked: bool = False,
    ) -> list[dict[str, str]]:
        if (
            duration_minutes < self.minimum_duration_minutes
            or duration_minutes > self.maximum_duration_minutes
        ):
            return []
        opening = time_to_minutes(self.opens_at)
        closing = time_to_minutes(self.closes_at)
        slots: list[dict[str, str]] = []
        for day in self.operating_days:
            start = opening
            while start + duration_minutes <= closing:
                end = start + duration_minutes
                slot = {
                    "day": day,
                    "start_time": minutes_to_time(start),
                    "end_time": minutes_to_time(end),
                }
                failures = self.validate_slot(**slot)
                blocked_only = failures and all(
                    failure.startswith("Slot overlaps blocked period:")
                    for failure in failures
                )
                if not failures or (include_blocked and blocked_only):
                    slots.append(slot)
                if len(slots) >= self.maximum_candidates_per_entry:
                    return slots
                start += self.slot_interval_minutes
        return slots


@dataclass(frozen=True)
class RankingWeights:
    confirmed_conflict_removed: int = 35
    inferred_conflict_removed: int = 8
    structural_clash_removed: int = 20
    conflict_group_removed: int = 12
    affected_student_penalty: int = 1
    day_distance_penalty: int = 4
    half_hour_shift_penalty: int = 1
    late_slot_penalty: int = 6
    conditional_data_penalty: int = 12
    insufficient_data_penalty: int = 30


DEFAULT_SCHEDULING_POLICY = SchedulingPolicy()
DEFAULT_RANKING_WEIGHTS = RankingWeights()
