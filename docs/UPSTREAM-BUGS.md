# yukic v0.1.0: three bugs found during integration (int→string garbage, bytes move semantics diagnostics, .apply() on array-of-class hangs)

**Environment:** yukic v0.1.0, pinned commit 753ee4e9374bb33b3dbbaf85028f7f66254207ff, built with LLVM 22, reproduced on both x86_64 and aarch64 in CI.

## Bug 1: int-to-string conversion returns garbage

Minimal reproduction (EXACT code block):

```
load std.io: print
load .strutil: i64_to_string

fun main() {
    print("v=" + i64_to_string(42) + "\n")
}
```

Actual output: v=5250
Expected output: v=42
Compiler output: no error, exit 0.

Helper source (user-supplied, EXACT verbatim code block):

```
public fun i64_to_string(v: int64) -> string {
    if v == 0 { return "0" }
    set neg = v < 0
    set n = v
    if neg { rewrite n = -n }
    set digits: bytes = cast("", "bytes")
    while n > 0 {
        digits.push(cast(48 + n % 10, "uint8"))
        rewrite n /= 10
    }
    set out = ""
    if neg { rewrite out = "-" }
    set ds: string = cast(digits, "string")
    set i2 = ds.len()
    while i2 > 0 {
        rewrite i2 -= 1
        rewrite out = out + cast(ds[i2], "string")
    }
    return out
}
```

Notes: The digit bytes themselves are correct — `cast(bytes, "string")` of a 1-byte buffer prints "A" correctly. Corruption appears when the loop indexes the string and concatenates via `cast(ds[i2], "string")`. Suspect string indexing returns a byte value rather than a 1-char string, or the concatenation of a cast byte is miscompiled. Also `set s: string = "v=" + i64_to_string(42)` yields "5250" AND `print("v=" + i64_to_string(42))` yields "5250" — so the returned string itself is wrong, not the caller.

Impact: numeric-to-string formatting silently corrupts program output.

## Bug 2: bytes parameter is move-consumed with conflicting diagnostics

Minimal reproduction (EXACT code block):

```
load std.io: print

fun take(x: bytes) -> string {
    return cast(x, "string")
}

fun main() {
    set a: bytes = cast("hi", "bytes")
    print(take(a) + "\n")
    print(take(a) + "\n")
}
```

Actual output: error[E0501]: use of moved value `a`
Workaround: the caller must write `take(a.cp())`.

Diagnostic conflict: at five call sites in the ypwee codebase, first `ref a` produced error[E0401]: expected `bytes`, found `ref bytes`; only after switching to plain `a` did error[E0501] appear. The two diagnostics point in opposite directions and neither suggests `.cp()`.

Upstream request: make value parameters non-consuming for the affine `bytes` type, or make the diagnostic say "consider .cp()".

Impact: repeated use of the same bytes value across calls is unusable without knowing an undocumented `.cp()` workaround.

## Bug 3: `.apply()` on array-of-class hangs at runtime (no minimal repro)

No publishable minimal reproduction exists; this was observed in a larger program. Calling `.apply(payload)` inside a loop over indexes into an indexed array `Aes256Ctr[]` whose elements are class instances hung the process with no output. Current code avoids the construct by storing one cipher per class field. Request: either make it work or reject it at compile time.

Impact: silent runtime hang with no diagnostic.

## Workarounds used in practice

- Lookup tables for int→string (Bug 1).
- `.cp()` before every repeated bytes argument (Bug 2).
- Avoid `.apply()` on array-of-class; store one cipher per class field (Bug 3).
