from mathpub.question import generator


@generator
def generate(ctx):
    angle_degrees = ctx.domain("angle_degrees", [20, 25, 30])
    length_metres = ctx.domain("length_metres", [25, 35, 45])
    gravity = QQ(98) / 10
    angle = angle_degrees * pi / 180
    vertical_drop = length_metres * sin(angle)
    speed = sqrt(2 * gravity * vertical_drop)

    # Diagram coordinates are physical metres. TikZ applies one common visual scale.
    ramp_run = length_metres * cos(angle)
    ramp_rise = vertical_drop

    ctx.parameter("angle_degrees", angle_degrees)
    ctx.parameter("length_metres", length_metres)
    ctx.parameter("gravity", gravity)
    ctx.derived("angle", angle)
    ctx.derived("vertical_drop", vertical_drop)
    ctx.derived("speed", speed)
    ctx.derived("ramp_run", ramp_run)
    ctx.derived("ramp_rise", ramp_rise)

    ctx.check_equal(
        "energy-conservation",
        QQ(1) / 2 * speed^2,
        gravity * length_metres * sin(angle),
        assumptions=("frictionless ramp", "starts from rest"),
    )
    ctx.check_equal(
        "diagram-ramp-length",
        ramp_run^2 + ramp_rise^2,
        length_metres^2,
    )
    ctx.check_close("diagram-ramp-angle", atan(ramp_rise / ramp_run), angle, atol=1e-12)
    ctx.validation_note(
        "energy-conservation",
        "Substituting the derived speed makes kinetic energy equal the lost gravitational potential energy.",
    )
    ctx.validation_note(
        "diagram-ramp-length",
        "The Pythagorean length of the generated run and rise equals the selected ramp length.",
    )
    ctx.validation_note(
        "diagram-ramp-angle",
        "The angle recovered from the generated rise and run equals the selected inclination.",
    )

    ctx.display.quantity("angle", angle_degrees, r"\degree")
    ctx.display.integer("angle_number", angle_degrees)
    ctx.display.quantity("length", length_metres, r"\meter")
    ctx.display.decimal("vertical_drop", vertical_drop, 2, unit=r"\meter")
    ctx.display.decimal("speed", speed, 1, unit=r"\meter\per\second")
    ctx.display.decimal("ramp_run", ramp_run, 8, trailing_zeros=False)
    ctx.display.decimal("ramp_rise", ramp_rise, 8, trailing_zeros=False)
