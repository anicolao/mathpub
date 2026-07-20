from mathpub.question import generator


@generator
def generate(ctx):
    roof_angle_degrees = ctx.random.integer(35, 45)
    barn_height = ctx.random.integer(8, 14)
    launch_speed = ctx.random.integer(4, 8)
    gravity = QQ(98) / 10
    angle = roof_angle_degrees * pi / 180
    horizontal_speed = launch_speed * cos(angle)
    vertical_speed = -launch_speed * sin(angle)
    impact_time = (vertical_speed + sqrt(vertical_speed^2 + 2 * gravity * barn_height)) / gravity
    impact_distance = horizontal_speed * impact_time

    # These are all physical-metre coordinates; TikZ applies one common scale.
    wall_x = 3
    roof_left_x = -1
    roof_left_y = barn_height + (wall_x - roof_left_x) * tan(angle)
    velocity_dx = 2 * cos(angle)
    velocity_dy = -2 * sin(angle)

    ctx.parameter("roof_angle_degrees", roof_angle_degrees)
    ctx.parameter("barn_height", barn_height)
    ctx.parameter("launch_speed", launch_speed)
    ctx.parameter("gravity", gravity)
    ctx.derived("horizontal_speed", horizontal_speed)
    ctx.derived("vertical_speed", vertical_speed)
    ctx.derived("impact_time", impact_time)
    ctx.derived("impact_distance", impact_distance)
    ctx.derived("roof_left_y", roof_left_y)

    ctx.check_equal(
        "vertical-impact-equation",
        barn_height
        + vertical_speed * impact_time
        - QQ(1) / 2 * gravity * impact_time^2,
        0,
        assumptions=("no air resistance", "level ground"),
    )
    ctx.check_equal("horizontal-impact-equation", impact_distance, horizontal_speed * impact_time)
    ctx.check_close(
        "diagram-roof-angle",
        atan((roof_left_y - barn_height) / (wall_x - roof_left_x)),
        angle,
        atol=1e-12,
    )
    ctx.check_close("diagram-launch-angle", atan(-velocity_dy / velocity_dx), angle, atol=1e-12)
    ctx.validation_note(
        "vertical-impact-equation",
        "The positive quadratic root is substituted into vertical position and returns ground level.",
    )
    ctx.validation_note(
        "horizontal-impact-equation",
        "The reported distance independently equals constant horizontal speed times flight time.",
    )
    ctx.validation_note(
        "diagram-roof-angle",
        "The generated roof rise and run recover the selected roof angle.",
    )
    ctx.validation_note(
        "diagram-launch-angle",
        "The launch arrow components recover the same angle and are tangent to the roof.",
    )

    ctx.display.quantity("roof_angle", roof_angle_degrees, r"\degree")
    ctx.display.integer("roof_angle_number", roof_angle_degrees)
    ctx.display.quantity("barn_height", barn_height, r"\meter")
    ctx.display.integer("barn_height_number", barn_height)
    ctx.display.quantity("launch_speed", launch_speed, r"\meter\per\second")
    ctx.display.decimal("impact_time", impact_time, 2, unit=r"\second")
    ctx.display.decimal("impact_distance", impact_distance, 1, unit=r"\meter")
    ctx.display.decimal("impact_x", wall_x + impact_distance, 8, trailing_zeros=False)
    ctx.display.integer("wall_x", wall_x)
    ctx.display.integer("roof_left_x", roof_left_x)
    ctx.display.decimal("roof_left_y", roof_left_y, 8, trailing_zeros=False)
    ctx.display.decimal("velocity_dx", velocity_dx, 8, trailing_zeros=False)
    ctx.display.decimal("velocity_dy", velocity_dy, 8, trailing_zeros=False)
