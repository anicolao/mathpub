from mathpub.question import generator


@generator
def generate(ctx):
    mass = ctx.random.integer(2, 12)
    height = ctx.random.integer(3, 18)
    gravity = QQ(98) / 10
    speed = sqrt(2 * gravity * height)

    ctx.parameter("mass", mass)
    ctx.parameter("height", height)
    ctx.parameter("gravity", gravity)
    ctx.derived("speed", speed)
    ctx.require("classroom-speed", speed < 20, "speed should remain below 20 m/s")
    ctx.check_equal("kinematic-identity", speed^2, 2 * gravity * height)
    ctx.check_equal(
        "energy-conservation",
        mass * gravity * height,
        QQ(1) / 2 * mass * speed^2,
        assumptions=("frictionless ramp", "starts from rest"),
    )

    ctx.display.quantity("mass", mass, r"\kilogram")
    ctx.display.quantity("height", height, r"\meter")
    ctx.display.decimal("gravity", gravity, 1, unit=r"\meter\per\second\squared")
    ctx.display.decimal("speed", speed, 2, unit=r"\meter\per\second")
