import numpy as np
from shapely import Polygon, LineString, Point


class ArenaEnv:
    def __init__(
        self,
        wall_dist=5,
        wall_height=1.0,
        num_walls=4,
        retina_dims=(50, 80),
        retina_scale=0.008,
        retina_pov_horizon=20,
        agent_height=0.5,
        agent_view_angle=1.5 * np.pi,
        agent_pov_dist=0.5,
    ):
        """
        Initialize the ArenaEnv class.

        Parameters:
        - wall_dist: float, the distance of the walls from the origin
        - wall_height: float, the height of the walls
        - num_walls: int, the number of walls in the environment
        - retina_dims: tuple, the dimensions of the retina (height, width)
        - retina_scale: float, the scaling factor for the retina
        - agent_height: float, the height of the agent
        - agent_view_angle: float, the angle of view for the agent
        - agent_pov_dist: float, the distance of the agent's point of view

        Returns: None
        """
        self.wall_dist = wall_dist
        self.wall_height = wall_height
        self.num_walls = num_walls

        self.retina_dims = retina_dims
        self.retina = np.zeros(self.retina_dims)
        self.retina_pov_horizon = retina_pov_horizon
        self.retina_scale = retina_scale

        self.agent_position = np.array((0.0, 0.0))
        self.agent_height = agent_height
        self.agent_view_angle = agent_view_angle
        self.agent_pov_dist = agent_pov_dist
        self.agent_direction = 0

        # Calculate the wall view angle
        wall_view_angle = 2 * np.pi / self.num_walls

        # Calculate the angles for each wall
        angles = np.array([wall_view_angle * i for i in range(self.num_walls)])

        # Concatenate the angles array with the first angle to form a loop
        angles = np.hstack([angles[: self.num_walls], angles[0]])

        # Adjust the angles to center the walls
        angles -= wall_view_angle / 2

        # Generate the wall coordinates based on the angles
        self.walls = Polygon(
            [
                [
                    self.wall_dist * np.cos(a),
                    self.wall_dist * np.sin(a),
                ]
                for a in angles
            ]
        )

    def reset(self):
        """Reset the environment."""
        pass

    def find_angle(self, p1, p2):
        """
        Calculate the angle between two points.

        Args:
            p1 (tuple): The coordinates of the first point (x1, y1).
            p2 (tuple): The coordinates of the second point (x2, y2).

        Returns:
            float: The angle between the two points in radians.
        """
        (x1, y1), (x2, y2) = p1, p2
        dx = x2 - x1
        dy = y2 - y1
        angle_rad = np.arctan2(dy, dx)
        angle_rad %= 2 * np.pi
        return angle_rad

    def step(self, speed, direction):
        """
        Take a step in the environment.

        Parameters:
        - speed: float, amount of total increment in the position of the agent
        - direction: float, the new direction of the agent

        Returns: ndarray, the retina output
        """

        # Update the agent's position, but only if it is not beyond the walls

        new_direction = self.agent_direction + direction
        new_position = self.agent_position + speed*np.array([
            np.cos(new_direction), np.sin(new_direction)])
        if self.walls.contains(Point(new_position)):
            self.agent_direction = new_direction
            self.agent_position[:] = new_position.copy()

        # update the agent's direction
        self.agent_direction = self.agent_direction % (2 * np.pi)
        angle_increment = self.agent_view_angle / self.retina_dims[1]

        # This code block calculates the angles between the agent's current
        # position and each edge of the walls.
        agent_edge_directions = np.array(
            [
                self.find_angle(self.agent_position, edge)
                for edge in np.array(self.walls.exterior.xy).T[:-1]
            ]
        )
        agent_edge_directions -= angle_increment
        agent_edge_directions %= 2 * np.pi

        self.retina *= 0

        # Iterate over each column of the retina
        retina_indices = np.arange(self.retina_dims[1])
        ray_angles = (
            -self.agent_view_angle / 2
            + retina_indices * angle_increment
            + angle_increment / 2
            + self.agent_direction
        )
        max_fov_distance = 2 * self.wall_dist

        # Compute the coordinates of all rays
        ray_directions = np.column_stack(
            [
                max_fov_distance * np.cos(ray_angles),
                max_fov_distance * np.sin(ray_angles),
            ]
        )
        ray_starts = np.tile(self.agent_position, (len(retina_indices), 1))
        ray_ends = ray_starts + ray_directions
        rays = np.column_stack([ray_starts, ray_ends])

        # Create LineString objects for all rays
        ray_lines = [LineString(ray.reshape(2, 2)) for ray in rays]

        # Compute the distances between the rays and the walls
        intersections = [
            self.walls.exterior.intersection(ray) for ray in ray_lines
        ]
        distances = np.array(
            [
                np.linalg.norm(
                    np.hstack(intersection.xy) - self.agent_position
                )
                for intersection in intersections
            ]
        )

        # Compute the base and height of the POV
        height = self.wall_height - self.agent_height
        base_tan_angle = self.agent_height / distances
        height_tan_angle = height / distances
        pov_base = base_tan_angle * self.agent_pov_dist
        pov_height = height_tan_angle * self.agent_pov_dist

        # Convert the POV coordinates to retina coordinates
        b = (pov_base / self.retina_scale).astype(int)
        h = (pov_height / self.retina_scale).astype(int)
        b = self.retina_pov_horizon - b
        h = self.retina_pov_horizon + h

        # Update the retina with the points of interest
        valid_b_indices = np.where((0 <= b) & (b < self.retina_dims[0]))
        valid_h_indices = np.where((0 <= h) & (h < self.retina_dims[0]))
        self.retina[
            b[valid_b_indices],
            retina_indices[valid_b_indices],
        ] = 1
        self.retina[
            h[valid_h_indices],
            retina_indices[valid_h_indices],
        ] = 1

        # Compute the lower bound angles by subtracting half of the angle
        # increment from ray angles
        lower_bounds = ray_angles - angle_increment / 2

        # Compute the upper bound angles by adding half of the angle increment
        # to ray angles
        upper_bounds = ray_angles + angle_increment / 2

        # Normalize the lower and upper bound angles to be between 0 and 2*pi
        lower_bounds %= 2 * np.pi
        upper_bounds %= 2 * np.pi

        # Reshape the lower bounds, upper bounds, and agent edge directions
        # arrays for comparison
        lb = lower_bounds.reshape(-1, 1)
        ub = upper_bounds.reshape(-1, 1)
        ad = agent_edge_directions.reshape(1, -1)

        # Determine the edges by checking if the lower bound is less than the
        # agent edge direction and if the agent edge direction is less than the
        # upper bound
        edges = (lb < ad) & (ad < ub)

        # Get the indices of the edges in the retina array
        edges_in_retina = np.where(edges)[0]

        # Reshape the column indices array for comparison with the wall
        # boundaries
        col = np.arange(self.retina_dims[0]).reshape(-1, 1)

        # Reshape the boundaries array for comparison with the column indices
        b = b.reshape(1, -1)
        h = h.reshape(1, -1)

        # Determine the inner wall boundaries by checking if the column index
        # is within the boundaries
        inner_wall = (b < col) & (col < h)

        # Set the values of the retina array to 1 where there are edges in the
        # inner wall
        for e in edges_in_retina:
            self.retina[:, e] = 1 * inner_wall[:, e]

        # Return the updated retina
        return self.retina[::-1]

class GraphArena(ArenaEnv):
    """Class for creating a graphical representation of the environment"""

    def __init__(self, *args, **kargs):
        """Initialize the graphical representation of the environment"""
        super(GraphArena, self).__init__(*args, **kargs)
        self.fig, self.axes = plt.subplots(2, 1, figsize=(6, 8))
        self.g_retina = self.axes[0].imshow(
            np.zeros(self.retina_dims), cmap=plt.cm.binary, vmin=0, vmax=1
        )
        self.axes[0].set_axis_off()

        self.axes[1].set_axis_off()
        self.axes[1].set_aspect('equal')
        self.g_walls, = self.axes[1].plot(*self.walls.exterior.xy, c="black", lw=2)
        self.g_agent = self.axes[1].scatter(0, 0, s=100, c='#888')
        (self.g_agent_nose,) = self.axes[1].plot([0, 0.01], [0, 0], c='black')

    def step(self, *args, **kargs):
        """Step the environment and update the graphical representation"""
        super(GraphArena, self).step(*args, **kargs)
        self.g_retina.set_data(0.2 + 0.8*self.retina)
        self.g_agent.set_offsets(self.agent_position.reshape(1, -1))

        # Calculate the position of the agent's nose
        nose = self.agent_position + np.stack(
            [
                [0, 0],
                0.3
                * np.array(
                    [
                        np.cos(self.agent_direction),
                        np.sin(self.agent_direction),
                    ]
                ),
            ]
        )
        self.g_agent_nose.set_data(*nose.T)

if __name__ == '__main__':

    # import matplotlib library
    import matplotlib.pyplot as plt
    import mkvideo

    # close all existing plots
    plt.close('all')

    # enable interactive mode
    plt.ion()

    # create GraphArena object
    arena = GraphArena()

    # loop through time from 0 to 4*pi with 800 steps
    for t in np.linspace(0, 4*np.pi, 80000):
        # step the arena with parameters 0.015 and 0.01*(2*np.cos(t)-1)
        r = arena.step(0.015, 0.01*(2*np.cos(t)-1))
        # pause for 0.01 seconds
        plt.pause(0.01)

    # close all plots
    plt.close('all')