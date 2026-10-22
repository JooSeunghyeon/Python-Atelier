def square_evens(numbers):
    result = []
    for n in numbers:
        if n % 2 == 0:
            result.append(n * n)
    return result


if __name__ == "__main__":
    values = [1, 2, 3, 4, 5, 6]
    print(square_evens(values))
