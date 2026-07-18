from mathpub.question import generator


@generator
def generate(ctx):
    roof_angle_degrees = ctx.random.integer(35, 45)
    barn_height_metres = ctx.random.integer(8, 14)
    launch_speed = ctx.random.integer(4, 8)
    gravity = QQ(98) / 10
    roof_angle = roof_angle_degrees * pi / 180
    horizontal_speed = launch_speed * cos(roof_angle)
    vertical_speed = -launch_speed * sin(roof_angle)
    impact_time = (vertical_speed + sqrt(vertical_speed^2 + 2 * gravity * barn_height_metres)) / gravity
    impact_distance = horizontal_speed * impact_time

    # Both axes use the same physical scale: one centimetre represents 2.5 metres.
    centimetres_per_metre = QQ(2) / 5
    edge_height = barn_height_metres * centimetres_per_metre
    impact_x = impact_distance * centimetres_per_metre
    roof_dx = 2
    roof_dy = roof_dx * tan(roof_angle)
    velocity_dx = QQ(3) / 2 * cos(roof_angle)
    velocity_dy = -QQ(3) / 2 * sin(roof_angle)

    coordinates = []
    for index in range(21):
        time = impact_time * index / 20
        x = horizontal_speed * time * centimetres_per_metre
        y = (
            barn_height_metres
            + vertical_speed * time
            - QQ(1) / 2 * gravity * time^2
        ) * centimetres_per_metre
        coordinates.append(f"({float(x):.6f},{max(0, float(y)):.6f})")

    ctx.parameter("roof_angle_degrees", roof_angle_degrees)
    ctx.parameter("barn_height_metres", barn_height_metres)
    ctx.parameter("launch_speed", launch_speed)
    ctx.parameter("gravity", gravity)
    ctx.derived("horizontal_speed", horizontal_speed)
    ctx.derived("vertical_speed", vertical_speed)
    ctx.derived("impact_time", impact_time)
    ctx.derived("impact_distance", impact_distance)
    ctx.derived("edge_height", edge_height)
    ctx.derived("impact_x", impact_x)

    ctx.require("visible-impact", impact_distance > 1)
    ctx.check_equal(
        "trajectory-lands-on-ground",
        barn_height_metres
        + vertical_speed * impact_time
        - QQ(1) / 2 * gravity * impact_time^2,
        0,
        assumptions=("no air resistance", "level ground"),
    )
    ctx.check_equal("horizontal-motion", impact_distance, horizontal_speed * impact_time)
    ctx.check_close(
        "diagram-launch-angle",
        atan(-velocity_dy / velocity_dx),
        roof_angle,
        atol=1e-12,
    )
    ctx.check_close(
        "diagram-impact-scale",
        impact_x / centimetres_per_metre,
        impact_distance,
        atol=1e-12,
    )

    ctx.display.quantity("roof_angle", roof_angle_degrees, r"\degree")
    ctx.display.integer("roof_angle_number", roof_angle_degrees)
    ctx.display.quantity("barn_height", barn_height_metres, r"\meter")
    ctx.display.quantity("launch_speed", launch_speed, r"\meter\per\second")
    ctx.display.decimal("impact_time", impact_time, 2, unit=r"\second")
    ctx.display.decimal("impact_distance", impact_distance, 1, unit=r"\meter")
    ctx.display.decimal("edge_height", edge_height, 6, trailing_zeros=False)
    ctx.display.decimal("impact_x", impact_x, 6, trailing_zeros=False)
    ctx.display.decimal("roof_dy", roof_dy, 6, trailing_zeros=False)
    ctx.display.decimal("velocity_dx", velocity_dx, 6, trailing_zeros=False)
    ctx.display.decimal("velocity_dy", velocity_dy, 6, trailing_zeros=False)
    ctx.display.tex("trajectory_coordinates", " ".join(coordinates))
