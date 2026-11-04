use super::*;

fn a_rig() -> RigDef {
    RigDef {
        glb: "models/person.glb".into(),
        clips: Clips {
            idle: "Idle".into(),
            walk: "Walk".into(),
            run: "Run".into(),
            wave: "Wave".into(),
            sit: "Sit".into(),
            lie: "Death".into(),
        },
        walk_ground_m_s: 1.4,
        run_ground_m_s: 3.5,
        run_above_m_s: 2.2,
        blend_s: 0.25,
        standing_height_m: 1.8,
        coat_slots: vec!["Shirt".into()],
        skin_slots: vec!["Skin".into()],
    }
}

fn weight_of(clips: &[Weighted], clip: Clip) -> f32 {
    clips.iter().filter(|w| w.clip == clip).map(|w| w.weight).sum()
}

fn rate_of(clips: &[Weighted], clip: Clip) -> f32 {
    clips.iter().find(|w| w.clip == clip).map(|w| w.rate).expect("clip shown")
}

#[test]
fn a_pose_is_named_as_the_manifest_names_it() {
    assert_eq!(Pose::Lying.name(), "lying");
}

#[test]
fn a_person_standing_still_idles() {
    let shown = locomotion(&a_rig(), 0.0, Pose::Standing);

    assert_eq!(weight_of(&shown, Clip::Idle), 1.0);
}

#[test]
fn a_walking_person_plays_the_walk_at_the_rate_its_feet_cover_the_ground() {
    let shown = locomotion(&a_rig(), 1.0, Pose::Standing);

    assert_eq!(weight_of(&shown, Clip::Walk), 1.0);
    assert!((rate_of(&shown, Clip::Walk) - 1.0 / 1.4).abs() < 1e-5);
}

#[test]
fn a_fleeing_person_runs_at_the_rate_its_feet_cover_the_ground() {
    let shown = locomotion(&a_rig(), 4.0, Pose::Standing);

    assert_eq!(weight_of(&shown, Clip::Run), 1.0);
    assert!((rate_of(&shown, Clip::Run) - 4.0 / 3.5).abs() < 1e-5);
}

#[test]
fn walking_crosses_into_running_with_weights_that_sum_to_one() {
    let rig = a_rig();

    for speed in [2.0, 2.1, 2.2, 2.3, 2.4] {
        let shown = locomotion(&rig, speed, Pose::Standing);
        let total: f32 = shown.iter().map(|w| w.weight).sum();
        assert!((total - 1.0).abs() < 1e-5, "{speed}: {shown:?}");
    }
    let at_threshold = locomotion(&rig, 2.2, Pose::Standing);
    assert!(weight_of(&at_threshold, Clip::Walk) > 0.0 && weight_of(&at_threshold, Clip::Run) > 0.0);
}

#[test]
fn a_survivor_who_is_not_moving_holds_their_pose() {
    let rig = a_rig();

    let shown: Vec<f32> = [(Pose::Lying, Clip::Lie), (Pose::Sitting, Clip::Sit), (Pose::Waving, Clip::Wave)]
        .into_iter()
        .map(|(pose, clip)| weight_of(&locomotion(&rig, 0.0, pose), clip))
        .collect();

    assert_eq!(shown, vec![1.0, 1.0, 1.0]);
}

#[test]
fn a_posed_person_who_moves_walks() {
    let shown = locomotion(&a_rig(), 1.2, Pose::Waving);

    assert_eq!(weight_of(&shown, Clip::Walk), 1.0);
}

#[test]
fn a_looping_clip_wraps_and_each_person_starts_at_their_own_phase() {
    let a = clip_time(10.0, 0.0, 1.0, 1.2, true);
    let b = clip_time(10.0, 0.5, 1.0, 1.2, true);

    assert!((0.0..1.2).contains(&a) && (0.0..1.2).contains(&b));
    assert!((a - b).abs() > 1e-3);
    assert_eq!(a, clip_time(10.0, 0.0, 1.0, 1.2, true));
}

#[test]
fn a_held_clip_stops_on_its_last_frame() {
    assert_eq!(clip_time(30.0, 0.25, 1.0, 2.0, false), 2.0);
}

#[test]
fn a_person_is_scaled_to_their_height() {
    let rig = a_rig();

    assert_eq!((rig_scale(&rig, Some(1.62)), rig_scale(&rig, None)), (0.9, 1.0));
}

#[test]
fn a_rig_whose_run_covers_less_ground_than_its_walk_is_refused_by_name() {
    let rig = RigDef { run_ground_m_s: 1.0, ..a_rig() };

    assert!(rig.validate().unwrap_err().contains("run_ground_m_s"));
}

#[test]
fn a_rig_that_is_not_gltf_is_refused_by_name() {
    let rig = RigDef { glb: "models/person.fbx".into(), ..a_rig() };

    assert!(rig.validate().unwrap_err().contains("person.fbx"));
}
