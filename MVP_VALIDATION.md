# mathpub MVP generation and validation

This document specifies the executable trust boundary for generated questions. It is separated
from [MVP_DESIGN.md](MVP_DESIGN.md) so generator authors and reviewers can focus on domains,
canonical values, mathematical evidence, and diagrams without conflating those concerns with page
assembly.

## 1. Generator contract

Each `generate.sage` runs in a fresh SageMath process. It registers one function and returns all
data through `ctx`:

```python
from mathpub.question import generator

@generator
def generate(ctx):
    angle = ctx.domain("angle_degrees", [20, 25, 30])
    length = ctx.domain("length_metres", [25, 35, 45])
    theta = angle * pi / 180
    speed = sqrt(2 * (QQ(98) / 10) * length * sin(theta))

    ctx.parameter("angle_degrees", angle)
    ctx.parameter("length_metres", length)
    ctx.derived("speed", speed)
    ctx.check_equal("energy", speed^2 / 2, (QQ(98) / 10) * length * sin(theta))
    ctx.display.decimal("speed", speed, 1, unit=r"\meter\per\second")
```

The supported proposal API is:

- `ctx.random.integer(low, high)`, inclusive;
- `ctx.random.choice(sequence)` and `ctx.random.rational(numerators, denominators)`;
- `ctx.domain(name, values)`, which permits exhaustive overrides from declared finite domains;
- `ctx.parameter(name, value)` and `ctx.derived(name, value)`;
- `ctx.require(name, condition, detail=None)`;
- `ctx.check_equal`, `ctx.check_close`, and `ctx.check_true`; and
- `ctx.display.text`, `integer`, `decimal`, `significant`, `math`, `quantity`, and trusted `tex`.

Generator source must not use ambient Python, NumPy, or Sage random state. `mathpub check` lints common
global-random calls and runs sampled instances twice in independent Sage processes.

## 2. Canonical values and presentation values

Parameters and derived values retain exact integers, rationals, algebraic values, and symbolic
expressions. Display values are a separate, explicit formatting layer. Rounding a displayed answer
must never replace the exact canonical answer used by checks.

Canonical JSON uses tagged values and stable key ordering. For example:

```json
{"type":"rational","numerator":49,"denominator":5}
```

Every instance ends with a SHA-256 hash. Student, answer, and solution projections consume that
same stored instance; rendering never reruns a generator.

## 3. Constraints are not checks

`ctx.require` rejects an unsuitable proposal, such as an unreadable diagram or a degenerate root.
Generation then advances to the next deterministic attempt. Exhausting `max_attempts` is an error
and reports rejection counts.

A `ctx.check_*` call tests the accepted mathematical model. Failure stops the build immediately;
it is never retried as random bad luck. Evidence records contain a stable ID, status, evidence type,
backend, assumptions, and details. Sage evidence may be symbolic, exact, numerical-residual,
sampled, or exhaustive. It must not be described as a formal proof.

Question-local seeds are derived from root seed, variant, question ID, and attempt using SHA-256,
then passed to pinned NumPy PCG64. Publication order therefore cannot alter unrelated instances.

## 4. Worked validation: `k-rampy`

The migrated [`k-rampy`](questions/physics/energy/k-rampy/question.toml) problem chooses a ramp
angle $\theta$ and physical length $L$. Its canonical model derives

\[
  h=L\sin\theta,
  \qquad
  v=\sqrt{2gh}.
\]

It performs three distinct checks:

1. `energy-conservation` verifies $v^2/2=gL\sin\theta$ exactly.
2. `diagram-length-scale` verifies $x_d^2+y_d^2=(sL)^2$, where $s$ is the declared drawing scale.
3. `diagram-angle` verifies $\operatorname{atan2}(y_d,x_d)=\theta$ to a declared residual.

The prompt draws the ramp from the checked Cartesian coordinates. The angle arc, block rotation,
length marker, and text all consume the same instance. A label cannot say $30^\circ$ while a
hard-coded line depicts another angle.

The finite validation domain contains every combination of angles 20, 25, and 30 degrees with
lengths 25, 35, and 45 metres. Run it with:

```console
nix run .#mathpub -- check question physics.energy.k-rampy --exhaustive --json
```

## 5. Worked validation: barn-roof snowball

The migrated [`proj-snowball.q`](questions/physics/projectiles/snowball/question.toml) problem uses
a barn height $h$, roof angle $\theta$, and launch speed $v_0$. The snowball leaves tangent to the
downward roof:

\[
  v_x=v_0\cos\theta,
  \qquad
  v_y=-v_0\sin\theta.
\]

The positive impact time solves

\[
  0=h+v_y t-\frac12gt^2,
  \qquad x=v_xt.
\]

The checks substitute the computed time back into the vertical equation, independently verify
horizontal motion, recover the launch angle from the drawn velocity-vector components, and verify
the impact coordinate against the common physical scale. The plotted trajectory is sampled from
the same checked parametric equation. Horizontal and vertical axes use the same scale, so the
diagram can be measured meaningfully.

## 6. Diagram validation rules

A parameterized diagram is mathematical output, not decoration. Validation examples follow these
rules:

- geometric coordinates are derived values, never unrelated hard-coded stand-ins;
- both axes use one stated physical scale unless an explicitly schematic figure says otherwise;
- angle arcs and rotated objects use the generated angle;
- plotted curves use the checked equation and terminate at checked endpoints;
- dimensions and labels consume the same canonical instance as the geometry; and
- geometry checks appear in the manifest beside the physics checks.

Decorative offsets, arrow lengths, and label positions may be fixed when they do not represent a
physical measurement. Such values must not masquerade as data.

## 7. Sampled and exhaustive validation

`mathpub check question ID --seeds N` runs deterministic sampled-property checks, twice per seed,
and returns all evidence in versioned JSON. `--exhaustive` enumerates the Cartesian product in each
declared `testing.exhaustive_domains` table through `ctx.domain` overrides.

Exhaustive reports state the number of combinations and accepted or rejected instances. They apply
only to the declared finite teaching domain; they are not a universal proof over real-valued input.

## 8. Review notes and limits

- Symbolic equality is only as strong as its assumptions and Sage's simplification model.
- Numerical residuals must state tolerances and cannot establish exact equality.
- Diagram checks validate geometry; a human still reviews legibility, pedagogy, and annotation.
- Trusted TeX is local executable input. Shell escape remains disabled, but TeX is not a hostile-code
  sandbox.
- Formal-proof evidence is reserved for a future proof backend and kernel-checked artifact.

The validation worksheet is
[`publications/physics-validation.toml`](publications/physics-validation.toml). It builds student,
answer, and worked-solution projections from the same instances.
