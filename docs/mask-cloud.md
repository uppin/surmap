# SAM mask registration

Mask registration is `surmap.survey.mask_cloud.points_in_mask`. It keeps
camera-frame cloud points whose pinhole projection falls inside a SAM
polygon and inside the frame, drops points at or nearer than 5 cm, and
transforms the survivors with the RTAB-Map pose (`to_map_frame`) when one
is supplied. The result is a registration layer. It is not written into
RTAB-Map. The `surmap_fuse` ROS2 node, including landmark provenance,
remains the design in [architecture.md](architecture.md); this function
is the projection that node performs.

The point-to-pixel link is recovered by projecting camera-frame `xyz`
with the stereo rig. `points_in_mask` keeps the points whose pixel lies
inside the mask polygon and the frame.
