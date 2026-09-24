"""Source-faithful NAACCR Vol V ER7 to canonical intake envelopes.

Segment field access and MLLP boundary handling were adapted from
IHE-SDC-WG/LRI-Validator at 00db61bc10e3ca85f297c88c553a837bb80f1c3a.
That project's ballot-draft validation rules are deliberately not an ingest gate.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

PARSER_NAME = "sdc-cdm-hl7v2"
PARSER_VERSION = "1"
MEDIA_TYPE = "application/hl7-v2+er7"

METADATA_LOINCS = {"60573-3", "60572-5", "60574-1"}
SYNOPTIC_LOINCS = {"60568-3", "60571-7", "60569-1"}
NARRATIVE_LOINCS = {"35265-8", "33716-2", "33717-0"}
TUMOR_SITE_CODES = {"2118.1000043", "22371.100004300", "48385.100004300"}
PROCEDURE_CODES = {"820603.1000043", "51121.100004300"}
LATERALITY_CODES = {"52756.1000043", "8722.100004300"}
COMMENT_CODES = {"2168.1000043"}
CAP_CODE = re.compile(r"^[0-9]+\.[0-9]+(?:__[1-9][0-9]*)?$")
NUMBER = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
HL7_DATE = re.compile(r"^(\d{4}(?:\d{2}){0,5})([+-]\d{4})?$")


class Hl7ParseError(ValueError):
    """The message cannot produce a trustworthy envelope."""


@dataclass(frozen=True, slots=True)
class Segment:
    name: str
    parts: tuple[str, ...]
    line: int

    def field(self, number: int) -> str:
        if self.name == "MSH":
            if number == 1:
                return "|"
            number -= 1
        return self.parts[number] if number < len(self.parts) else ""


def _component(value: str, number: int) -> str:
    parts = value.split("^")
    return parts[number - 1] if number <= len(parts) else ""


def _segments(raw: bytes) -> list[Segment]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Hl7ParseError("HL7 message is not UTF-8") from exc
    text = text.strip(" \t\r\n")
    if text.startswith("\x0b"):
        if text.endswith("\x1c\r"):
            text = text[1:-2]
        elif text.endswith("\x1c"):
            text = text[1:-1]
        else:
            raise Hl7ParseError("incomplete MLLP frame")
    elif "\x0b" in text or "\x1c" in text:
        raise Hl7ParseError("embedded MLLP frame")
    lines = [line for line in re.split(r"\r\n|\r|\n", text) if line.strip()]
    if not lines or sum(line.startswith("MSH|") for line in lines) != 1:
        raise Hl7ParseError("exactly one MSH segment is required")
    if lines[0].startswith(("FHS|", "BHS|")) or not lines[0].startswith("MSH|"):
        raise Hl7ParseError("message must start with MSH")
    return [Segment(line[:3], tuple(line.split("|")), index) for index, line in enumerate(lines, 1)]


def decode_hl7(value: str) -> str:
    """Decode ER7 escapes after field splitting, including hexadecimal CR/LF."""

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        simple = {"F": "|", "S": "^", "T": "&", "R": "~", "E": "\\", ".br": "\n"}
        if token in simple:
            return simple[token]
        if token.startswith("X") and len(token) > 1 and len(token[1:]) % 2 == 0:
            try:
                return bytes.fromhex(token[1:]).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                pass
        return match.group(0)

    decoded = re.sub(r"\\([^\\]+)\\", replace, value)
    return decoded.replace("\r\n", "\n").replace("\r", "\n")


def parse_date(value: str, diagnostics: list[dict[str, str]], location: str) -> dict[str, Any] | None:
    if not value:
        return None
    match = HL7_DATE.fullmatch(value)
    if match is None or len(match.group(1)) not in {4, 6, 8, 10, 12, 14}:
        diagnostics.append(_diagnostic("INVALID_DATE", f"{location} has an unparseable date"))
        return None
    digits, offset = match.groups()
    year = int(digits[:4])
    month = int(digits[4:6]) if len(digits) >= 6 else None
    day = int(digits[6:8]) if len(digits) >= 8 else None
    hour = int(digits[8:10]) if len(digits) >= 10 else None
    minute = int(digits[10:12]) if len(digits) >= 12 else None
    second = int(digits[12:14]) if len(digits) >= 14 else None
    valid = 1 <= year <= 9999
    valid &= month is None or 1 <= month <= 12
    valid &= hour is None or 0 <= hour <= 23
    valid &= minute is None or 0 <= minute <= 59
    valid &= second is None or 0 <= second <= 59
    try:
        if month is not None and day is not None:
            date(year, month, day)
    except ValueError:
        valid = False
    if offset:
        offset_hour, offset_minute = int(offset[1:3]), int(offset[3:])
        valid &= len(digits) >= 10 and (offset_hour < 14 or (offset_hour == 14 and offset_minute == 0))
        valid &= offset_minute <= 59
    if not valid:
        diagnostics.append(_diagnostic("INVALID_DATE", f"{location} has an unparseable date"))
        return None
    precision = {4: "year", 6: "month", 8: "day", 10: "hour", 12: "minute", 14: "second"}[len(digits)]
    result: dict[str, Any] = {"y": year, "m": month, "d": day, "precision": precision}
    if len(digits) >= 10:
        result.update(hh=hour, mi=minute, ss=second)
    if offset:
        result["tz"] = f"{offset[:3]}:{offset[3:]}"
    return result


def _diagnostic(code: str, detail: str) -> dict[str, str]:
    return {"severity": "warning", "code": code, "detail": detail}


def _text(value: str) -> str | None:
    value = decode_hl7(value).strip()
    return value or None


def _sub_id(value: str) -> str | None:
    return value.lstrip("+").split(".", 1)[0] or None


def _obx_components(obx: Segment, diagnostics: list[dict[str, str]]) -> tuple[str, str | None, str | None]:
    raw = obx.field(5)
    value_type = obx.field(2)
    if value_type in {"CE", "CWE"}:
        code = _text(_component(raw, 1))
        return "coded" if code else "text", code, None if code else _text(raw)
    if value_type == "NM" or (value_type == "ST" and NUMBER.fullmatch(raw)):
        if NUMBER.fullmatch(raw):
            return "numeric", raw, None
        diagnostics.append(_diagnostic("INVALID_NUMBER", f"OBX at line {obx.line} is not numeric"))
    return "text", None, _text(raw)


def _values(obx_segments: list[Segment], report_date: dict[str, Any] | None,
            diagnostics: list[dict[str, str]]) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    active: dict[tuple[str, str], dict[str, Any]] = {}
    for obx in obx_segments:
        code = _component(obx.field(3), 1)
        if code in METADATA_LOINCS or code in COMMENT_CODES:
            continue
        if not CAP_CODE.fullmatch(code):
            diagnostics.append(_diagnostic("NON_CAP_IDENTIFIER", f"OBX at line {obx.line} has no CAP question code"))
            continue
        kind, value, text = _obx_components(obx, diagnostics)
        sub_id = _sub_id(obx.field(4))
        key = (code, sub_id or "")
        field = {"coded": "value_code", "numeric": "value_num", "text": "value_text"}[kind]
        existing = active.get(key) if sub_id else None
        if existing is None or field in existing:
            if existing is not None:
                diagnostics.append(_diagnostic("REPEATED_OBX_COMPONENT", f"OBX at line {obx.line} repeats {kind}"))
            existing = {"ecp_code": code}
            if sub_id:
                existing["obx_sub_id"] = sub_id
                active[key] = existing
            captured.append(existing)
        if kind == "text":
            if text is not None:
                existing[field] = text
        elif value is not None:
            existing[field] = value
        unit = _text(_component(obx.field(6), 1))
        if unit and "unit_source" not in existing:
            existing["unit_source"] = unit
        raw_date = obx.field(14)
        parsed_date = parse_date(raw_date, diagnostics, f"OBX-14 line {obx.line}") if raw_date else None
        if raw_date and parsed_date is None:
            existing["observation_date"] = None
        elif parsed_date is not None:
            existing.setdefault("observation_date", parsed_date)
        elif report_date is not None:
            existing.setdefault("observation_date", report_date)
            diagnostics.append(_diagnostic("OBX_DATE_FALLBACK", f"OBX-14 line {obx.line} uses OBR date"))
    return captured


def _report(obr: Segment, observations: list[Segment], diagnostics: list[dict[str, str]]) -> dict[str, Any]:
    loinc = _component(obr.field(4), 1)
    accession = _text(_component(obr.field(3), 1))
    raw_date = obr.field(7) or obr.field(22)
    report_date = parse_date(raw_date, diagnostics, f"OBR date line {obr.line}") if raw_date else None
    report: dict[str, Any] = {"report_loinc": loinc or None, "accession": accession}
    if raw_date:
        report["observation_date"] = report_date
    if loinc in NARRATIVE_LOINCS:
        narrative = "\n".join(filter(None, (_text(item.field(5)) for item in observations if item.field(2) in {"TX", "FT", "ST"})))
        if narrative:
            report["narrative"] = narrative
    else:
        metadata = {
            "60573-3": "template_source",
            "60572-5": "template_id",
            "60574-1": "template_version",
        }
        for item in observations:
            code = _component(item.field(3), 1)
            if code in metadata:
                value = _text(_component(item.field(5), 1))
                if value:
                    report[metadata[code]] = value
            if code in TUMOR_SITE_CODES:
                report.setdefault("tumor_site", _text(item.field(5)))
            if code in PROCEDURE_CODES:
                report.setdefault("procedure", _text(item.field(5)))
            if code in LATERALITY_CODES:
                report.setdefault("laterality", _text(item.field(5)))
            if code in COMMENT_CODES and _text(item.field(5)):
                report.setdefault("narrative", _text(item.field(5)))
    return report


def parse_hl7(raw: bytes) -> list[dict[str, Any]]:
    """Parse one ER7 byte stream to one envelope per OBR in source order."""

    segments = _segments(raw)
    msh = segments[0]
    if msh.field(9) != "ORU^R01^ORU_R01":
        raise Hl7ParseError("message type must be ORU^R01^ORU_R01")
    pid = next((item for item in segments if item.name == "PID"), None)
    if pid is None:
        raise Hl7ParseError("PID segment is missing")
    pid3 = pid.field(3).split("~", 1)[0]
    source_id = _component(pid3, 1)
    if not source_id:
        raise Hl7ParseError("PID-3 patient identifier is missing")
    patient: dict[str, Any] = {
        "person_source_value": source_id,
        "assigning_authority": _component(pid3, 4),
    }
    if pid.field(8):
        patient["gender"] = pid.field(8)
    sha = hashlib.sha256(raw).hexdigest()
    raw_info = {"sha256": sha, "byte_length": len(raw), "media_type": MEDIA_TYPE}
    orc = next((item for item in segments if item.name == "ORC"), None)
    episode_source = _component(orc.field(4), 1) if orc else ""
    episode_authority = _component(orc.field(4), 3) if orc else ""
    obrs = [i for i, item in enumerate(segments) if item.name == "OBR"]
    if not obrs:
        raise Hl7ParseError("OBR segment is missing")
    envelopes: list[dict[str, Any]] = []
    for ordinal, start in enumerate(obrs, 1):
        end = obrs[ordinal] if ordinal < len(obrs) else len(segments)
        obr = segments[start]
        observations = [item for item in segments[start + 1:end] if item.name == "OBX"]
        diagnostics: list[dict[str, str]] = []
        birth = pid.field(7)
        if birth:
            patient = {**patient, "birth_date": parse_date(birth, diagnostics, "PID-7")}
        report = _report(obr, observations, diagnostics)
        source: dict[str, Any] = {"format": "hl7v2", "obr_ordinal": ordinal}
        for field, value in (
            ("message_control_id", msh.field(10)),
            ("sending_facility", msh.field(4)),
            ("message_profile", msh.field(21)),
        ):
            if value:
                source[field] = value
        envelope: dict[str, Any] = {
            "envelope_version": "1",
            "source": source,
            "raw": raw_info,
            "patient": patient,
            "report": report,
        }
        if episode_source:
            envelope["episode"] = {"episode_source_value": episode_source}
            if episode_authority:
                envelope["episode"]["assigning_authority"] = episode_authority
        if report.get("report_loinc") not in NARRATIVE_LOINCS:
            values = _values(observations, report.get("observation_date"), diagnostics)
            if values:
                envelope["values"] = values
        if diagnostics:
            envelope["diagnostics"] = diagnostics
        envelopes.append(envelope)
    return envelopes


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items() if item != {} and item != []}
    if isinstance(value, list):
        return [_normalize(item) for item in value if item != {} and item != []]
    return value


def serialize_envelope(envelope: dict[str, Any]) -> bytes:
    return (json.dumps(_normalize(envelope), sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def parse_envelope(serialized: bytes) -> dict[str, Any]:
    return json.loads(serialized)
