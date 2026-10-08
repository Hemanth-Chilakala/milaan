CREATE OR REPLACE PYTHON3 SCALAR SCRIPT MILAAN_CORE.SIMILARITY(a VARCHAR(200), b VARCHAR(200)) RETURNS DOUBLE AS
def jaro_winkler(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    distance = max(len(left), len(right)) // 2 - 1
    distance = max(distance, 0)
    used_left, used_right = [False] * len(left), [False] * len(right)
    matches = 0
    for i, char in enumerate(left):
        for j in range(max(0, i - distance), min(i + distance + 1, len(right))):
            if not used_right[j] and char == right[j]:
                used_left[i] = used_right[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    a = [char for i, char in enumerate(left) if used_left[i]]
    b = [char for i, char in enumerate(right) if used_right[i]]
    transpositions = sum(x != y for x, y in zip(a, b, strict=True)) / 2
    score = (matches / len(left) + matches / len(right) + (matches - transpositions) / matches) / 3
    prefix = 0
    for x, y in zip(left[:4], right[:4], strict=False):
        if x != y:
            break
        prefix += 1
    return score + prefix * 0.1 * (1 - score) if score > 0.7 else score

def run(ctx):
    return jaro_winkler(ctx.a, ctx.b)
/
