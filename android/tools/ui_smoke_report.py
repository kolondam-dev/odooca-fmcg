"""Export test IDs, outcomes and timings without stdout, stack traces or properties."""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TEST_CLASS = "com.kolondam.odooca.field.InitialFlowTest"
EXPECTED_TESTS = {"loginValidationResumeNavigationAndLocationDenial"}


def main(results: Path, report: Path, started_ns: int) -> int:
    outcomes = {}
    for xml in sorted(results.rglob("TEST-*.xml")):
        if xml.stat().st_mtime_ns < started_ns:
            continue
        for case in ET.parse(xml).iter("testcase"):
            name = case.get("name")
            if case.get("classname") != TEST_CLASS or name not in EXPECTED_TESTS:
                continue
            outcome = "PASS"
            if case.find("skipped") is not None:
                outcome = "SKIPPED"
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "FAIL"
            duration = case.get("time", "")
            if not re.fullmatch(r"\d+(\.\d+)?", duration):
                duration = ""
            if name in outcomes:
                outcome = "DUPLICATE"
            outcomes[name] = (outcome, duration)

    with report.open("w", encoding="utf-8") as dest:
        dest.write("test\tresult\tseconds\n")
        for name in sorted(EXPECTED_TESTS):
            outcome, duration = outcomes.get(name, ("NOT_RUN", ""))
            dest.write(f"{name}\t{outcome}\t{duration}\n")
    return int(any(outcomes.get(name, ("NOT_RUN",))[0] != "PASS" for name in EXPECTED_TESTS))


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])))
