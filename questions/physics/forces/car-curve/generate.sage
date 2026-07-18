from mathpub.question import generator


@generator
def generate(ctx):
    mass_value = 100 * ctx.random.integer(8, 18)
    speed_value = ctx.random.integer(10, 28)
    radius_value = 5 * ctx.random.integer(5, 20)
    mass, speed, radius = var("m v r")
    force_expression = mass * speed^2 / radius
    force_value = force_expression.subs(
        {mass: mass_value, speed: speed_value, radius: radius_value}
    )

    ctx.parameter("mass", mass_value)
    ctx.parameter("speed", speed_value)
    ctx.parameter("radius", radius_value)
    ctx.derived("force_expression", force_expression)
    ctx.derived("force", force_value)
    ctx.require("reasonable-force", force_value < 25000)
    ctx.check_equal("newtons-second-law", force_expression * radius, mass * speed^2)
    ctx.check_equal(
        "numeric-substitution",
        force_value * radius_value,
        mass_value * speed_value^2,
    )
    ctx.check_close(
        "floating-residual",
        force_value,
        mass_value * speed_value^2 / radius_value,
        atol=1e-10,
    )
    ctx.validation_note(
        "newtons-second-law",
        "Multiplying the radial-force model by radius recovers mass times speed squared.",
    )
    ctx.validation_note(
        "numeric-substitution",
        "The exact selected mass, speed, and radius satisfy the unrounded force equation.",
    )
    ctx.validation_note(
        "floating-residual",
        "An independent floating-point evaluation agrees within the declared tolerance.",
    )

    ctx.display.quantity("mass", mass_value, r"\kilogram")
    ctx.display.quantity("speed", speed_value, r"\meter\per\second")
    ctx.display.quantity("radius", radius_value, r"\meter")
    ctx.display.math("force_expression", force_expression)
    ctx.display.decimal("force", force_value, 0, unit=r"\newton")
