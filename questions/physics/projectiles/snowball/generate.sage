from mathpub.question import generator


@generator
def generate(ctx):
    launch_speed = ctx.random.integer(12, 26)
    angle_degrees = ctx.random.choice([30, 35, 40, 45, 50, 55, 60])
    gravity = QQ(98) / 10
    angle = angle_degrees * pi / 180
    flight_time = 2 * launch_speed * sin(angle) / gravity
    horizontal_speed = launch_speed * cos(angle)
    range_value = horizontal_speed * flight_time
    maximum_height = launch_speed^2 * sin(angle)^2 / (2 * gravity)

    ctx.parameter("launch_speed", launch_speed)
    ctx.parameter("angle_degrees", angle_degrees)
    ctx.parameter("gravity", gravity)
    ctx.derived("flight_time", flight_time)
    ctx.derived("range", range_value)
    ctx.derived("maximum_height", maximum_height)
    ctx.require("visible-range", 10 < range_value < 70)
    ctx.check_equal(
        "range-identity",
        range_value,
        launch_speed^2 * sin(2 * angle) / gravity,
        assumptions=("level launch and landing", "no air resistance"),
    )
    ctx.check_equal(
        "vertical-return",
        launch_speed * sin(angle) * flight_time
        - QQ(1) / 2 * gravity * flight_time^2,
        0,
    )

    ctx.display.quantity("launch_speed", launch_speed, r"\meter\per\second")
    ctx.display.quantity("angle", angle_degrees, r"\degree")
    ctx.display.decimal("gravity", gravity, 1, unit=r"\meter\per\second\squared")
    ctx.display.decimal("flight_time", flight_time, 2, unit=r"\second")
    ctx.display.decimal("range", range_value, 2, unit=r"\meter")
    ctx.display.decimal("maximum_height", maximum_height, 2, unit=r"\meter")
