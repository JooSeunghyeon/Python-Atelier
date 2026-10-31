from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    name: str
    score: int
    input_order: int


def build_records() -> list[Record]:
    raw = [
        ("dana", 80),
        ("alice", 90),
        ("bora", 80),
        ("chris", 90),
        ("eun", 70),
        ("fiona", 80),
    ]
    return [Record(name, score, idx) for idx, (name, score) in enumerate(raw)]


def check_stability(label: str, ordered: list[Record]) -> bool:
    print(f"[{label}]")
    for rec in ordered:
        print(f"  {rec.name:<6} score={rec.score} input_order={rec.input_order}")

    groups: dict[int, list[int]] = {}
    for rec in ordered:
        groups.setdefault(rec.score, []).append(rec.input_order)

    stable = True
    for score, orders in groups.items():
        if orders != sorted(orders):
            stable = False
            print(f"  -> score {score} 그룹의 입력 순서가 깨졌다: {orders}")
    print(f"  결과: {'유지됨' if stable else '깨짐'}\n")
    return stable


def main() -> None:
    records = build_records()

    by_score = sorted(records, key=lambda r: r.score)
    check_stability("sorted, key=score", by_score)

    by_score_name = sorted(records, key=lambda r: (r.score, r.name))
    check_stability("sorted, key=(score, name)", by_score_name)

    reversed_copy = list(records)
    reversed_copy.sort(key=lambda r: r.score, reverse=True)
    check_stability("list.sort, key=score, reverse=True", reversed_copy)


if __name__ == "__main__":
    main()
