def filter_lines(lines):
    stripped = (line.strip() for line in lines)
    non_empty = (line for line in stripped if line)
    return (line for line in non_empty if not line.startswith("#"))


if __name__ == "__main__":
    sample = [
        "import os",
        "",
        "# 설정",
        "   ",
        "DEBUG = True",
        "  # 들여쓴 주석",
        "PORT = 8000",
    ]

    result = list(filter_lines(sample))
    print(result)
