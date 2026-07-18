from mathpub.question import generator


@generator
def generate(ctx):
    angle_degrees = ctx.domain("angle_degrees", [20, 25, 30])
    length_metres = ctx.domain("length_metres", [25, 35, 45])
    gravity = QQ(98) / 10
    angle = angle_degrees * pi / 180
    height = length_metres * sin(angle)
    speed = sqrt(2 * gravity * height)

    # A fixed physical scale makes every drawn centimetre represent 8 metres.
    centimetres_per_metre = QQ(1) / 8
    diagram_run = length_metres * cos(angle) * centimetres_per_metre
    diagram_rise = height * centimetres_per_metre

    ctx.parameter("angle_degrees", angle_degrees)
    ctx.parameter("length_metres", length_metres)
    ctx.parameter("gravity", gravity)
    ctx.derived("angle", angle)
    ctx.derived("height", height)
    ctx.derived("speed", speed)
    ctx.derived("diagram_run", diagram_run)
    ctx.derived("diagram_rise", diagram_rise)

    ctx.check_equal(
        "energy-conservation",
        QQ(1) / 2 * speed^2,
        gravity * length_metres * sin(angle),
        assumptions=("frictionless ramp", "starts from rest"),
    )
    ctx.check_equal(
        "diagram-length-scale",
        diagram_run^2 + diagram_rise^2,
        (length_metres * centimetres_per_metre)^2,
    )
    ctx.check_close(
        "diagram-angle",
        atan(diagram_rise / diagram_run),
        angle,
        atol=1e-12,
    )

    ctx.display.quantity("angle", angle_degrees, r"\degree")
    ctx.display.integer("angle_number", angle_degrees)
    ctx.display.quantity("length", length_metres, r"\meter")
    ctx.display.decimal("height", height, 2, unit=r"\meter")
    ctx.display.decimal("speed", speed, 1, unit=r"\meter\per\second")
    ctx.display.decimal("diagram_run", diagram_run, 6, trailing_zeros=False)
    ctx.display.decimal("diagram_rise", diagram_rise, 6, trailing_zeros=False)
