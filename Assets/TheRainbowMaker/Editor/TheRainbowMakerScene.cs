// Builds The Rainbow Maker's scene: a graphite room with a big window, the solar Rainbow Maker (modelled in Blender,
// Art/rainbow-maker/) stuck to the glass, its baked gear loop on an Animator, and six coloured spot lights riding the
// crystal shaft so the rainbows sweep the room. Run from the menu, the agent queue (menu TheRainbowMaker/Build Scene),
// or batchmode: -executeMethod TheRainbowMakerScene.BuildBatch (only while the project is closed).
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class TheRainbowMakerScene
{
    const string Root = "Assets/TheRainbowMaker";
    const string Fbx = Root + "/RainbowMaker/rainbow-maker-20261022.fbx";
    const string MatDir = Root + "/RainbowMaker/Materials";
    const string Controller = Root + "/RainbowMaker/rainbow-maker-20261022.controller";
    const string ScenePath = Root + "/Scenes/the-rainbow-maker-20261022.unity";
    const string WorldPrefab = "Packages/com.vrchat.worlds/Samples/UdonExampleScene/Prefabs/VRCWorld.prefab";
    const float MakerScale = 10f;   // the real one is ~14 cm; ten times makes it 1.4 m on the window

    [MenuItem("TheRainbowMaker/Build Scene")]
    public static void Build()
    {
        ImportModel();
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        BuildRoom();
        var maker = PlaceMaker();
        AddRainbowLights(maker);
        PlaceSpawn();
        Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
        EditorSceneManager.SaveScene(scene, ScenePath);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
        Snapshot(maker);
        Debug.Log("TheRainbowMakerScene: built " + ScenePath);
    }

    public static void BuildBatch()
    {
        Build();
        AssetDatabase.SaveAssets();
    }

    // ---------- model: materials, looping clip, controller ----------
    static void ImportModel()
    {
        var imp = (ModelImporter)AssetImporter.GetAtPath(Fbx);
        imp.animationType = ModelImporterAnimationType.Generic;
        imp.importCameras = false;
        imp.importLights = false;
        foreach (var (name, color, metal, smooth, alpha, emit) in new[] {
            ("rm_clear_plastic", new Color(0.85f, 0.92f, 1f), 0f, 0.95f, 0.12f, 0f),
            ("rm_crystal",       new Color(0.95f, 0.97f, 1f), 0.5f, 1f, 0.45f, 0.15f),
            ("rm_gear_red",      new Color(0.95f, 0.05f, 0.12f), 0f, 0.6f, 1f, 0.25f),
            ("rm_gear_orange",   new Color(1f, 0.38f, 0f), 0f, 0.6f, 1f, 0.25f),
            ("rm_gear_yellow",   new Color(1f, 0.85f, 0f), 0f, 0.6f, 1f, 0.25f),
            ("rm_gear_green",    new Color(0.1f, 0.85f, 0.15f), 0f, 0.6f, 1f, 0.25f),
            ("rm_gear_blue",     new Color(0.05f, 0.35f, 1f), 0f, 0.6f, 1f, 0.25f),
            ("rm_gear_purple",   new Color(0.55f, 0.1f, 0.9f), 0f, 0.6f, 1f, 0.25f),
            ("rm_copper_wire",   new Color(0.95f, 0.5f, 0.3f), 1f, 0.75f, 1f, 0f),
            ("rm_magnet_wheel",  new Color(0.35f, 0.25f, 0.15f), 0.8f, 0.65f, 1f, 0f),
            ("rm_steel",         new Color(0.8f, 0.8f, 0.82f), 1f, 0.8f, 1f, 0f),
            ("rm_solar_cell",    new Color(0.05f, 0.08f, 0.2f), 0.3f, 0.85f, 1f, 0f),
            ("rm_panel_back",    new Color(0.85f, 0.7f, 0.62f), 0f, 0.5f, 1f, 0f),
        })
        {
            var m = MakeMat(MatDir + "/" + name.Replace('_', '-') + "-20261022.mat", color, metal, smooth, alpha, emit);
            imp.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), name), m);
        }
        imp.SaveAndReimport();

        var clips = imp.defaultClipAnimations;
        foreach (var c in clips) { c.loopTime = true; c.name = "rainbow-maker-loop"; }
        imp.clipAnimations = clips.Take(1).ToArray();
        imp.SaveAndReimport();

        // Copy the FBX clip into its own asset, keeping only the curves of parts that turn. Keys on the model's root
        // would pin it to the world origin at 1x scale whenever the Animator plays.
        var src = AssetDatabase.LoadAllAssetsAtPath(Fbx).OfType<AnimationClip>().First(c => !c.name.StartsWith("__preview"));
        var clip = new AnimationClip { frameRate = src.frameRate };
        var kept = 0;
        var rotations = AnimationUtility.GetCurveBindings(src)
            .Where(b => b.path != "" && (b.propertyName.StartsWith("m_LocalRotation") || b.propertyName.StartsWith("localEulerAngles")))
            .GroupBy(b => b.path);
        foreach (var part in rotations)
        {
            var curves = part.Select(b => (b, c: AnimationUtility.GetEditorCurve(src, b))).ToList();
            if (curves.All(x => x.c.keys.All(k => Mathf.Approximately(k.value, x.c.keys[0].value))))
                continue;   // a part that never moves (keep all four quaternion curves of parts that do)
            foreach (var (b, c) in curves) { AnimationUtility.SetEditorCurve(clip, b, c); kept++; }
        }
        var settings = AnimationUtility.GetAnimationClipSettings(clip);
        settings.loopTime = true;
        AnimationUtility.SetAnimationClipSettings(clip, settings);
        AssetDatabase.DeleteAsset(ClipPath);
        AssetDatabase.CreateAsset(clip, ClipPath);
        Debug.Log("TheRainbowMakerScene: clip kept " + kept + " rotation curves on "
                  + string.Join(", ", AnimationUtility.GetCurveBindings(clip).Select(b => b.path.Split('/').Last()).Distinct()));
        AssetDatabase.DeleteAsset(Controller);
        AnimatorController.CreateAnimatorControllerAtPathWithClip(Controller, clip);
        AssetDatabase.SaveAssets();
    }

    const string ClipPath = Root + "/RainbowMaker/rainbow-maker-loop-20261022.anim";
    static AnimationClip Clip() => AssetDatabase.LoadAssetAtPath<AnimationClip>(ClipPath);

    static Material MakeMat(string path, Color color, float metal, float smooth, float alpha, float emit)
    {
        var dir = Path.GetDirectoryName(path).Replace('\\', '/');
        if (!AssetDatabase.IsValidFolder(dir))
            AssetDatabase.CreateFolder(Path.GetDirectoryName(dir).Replace('\\', '/'), Path.GetFileName(dir));
        var m = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (m == null) { m = new Material(Shader.Find("Standard")); AssetDatabase.CreateAsset(m, path); }
        color.a = alpha;
        m.color = color;
        m.SetFloat("_Metallic", metal);
        m.SetFloat("_Glossiness", smooth);
        if (alpha < 1f)
        {   // Standard shader "Fade" mode
            m.SetFloat("_Mode", 2);
            m.SetOverrideTag("RenderType", "Transparent");
            m.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
            m.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
            m.SetInt("_ZWrite", 0);
            m.EnableKeyword("_ALPHABLEND_ON");
            m.renderQueue = 3000;
        }
        if (emit > 0f)
        {
            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", new Color(color.r, color.g, color.b) * emit);
        }
        EditorUtility.SetDirty(m);
        return m;
    }

    // ---------- room: graphite walls with neon trim, a big window on the north wall ----------
    static void BuildRoom()
    {
        var room = new GameObject("Room").transform;
        var wall = MakeMat(Root + "/Materials/graphite-20261022.mat", new Color(0.15f, 0.15f, 0.17f), 0f, 0.3f, 1f, 0f);
        var floor = MakeMat(Root + "/Materials/graphite-floor-20261022.mat", new Color(0.11f, 0.11f, 0.12f), 0.2f, 0.7f, 1f, 0f);
        var neon = MakeMat(Root + "/Materials/neon-pink-20261022.mat", new Color(1f, 0.1f, 0.65f), 0f, 0.5f, 1f, 2.5f);
        var glass = MakeMat(Root + "/Materials/window-glass-20261022.mat", new Color(0.75f, 0.9f, 1f), 0f, 1f, 0.08f, 0f);

        // 10 x 10 m room, 4 m tall; window opening 4 m wide, 2.6 m tall, sill at 0.8 m, centred on the north wall (z = 5).
        Box("Floor", room, new Vector3(0, -0.05f, 0), new Vector3(10, 0.1f, 10), floor);
        Box("Ceiling", room, new Vector3(0, 4.05f, 0), new Vector3(10, 0.1f, 10), wall);
        Box("WallSouth", room, new Vector3(0, 2, -5.05f), new Vector3(10, 4, 0.1f), wall);
        Box("WallEast", room, new Vector3(5.05f, 2, 0), new Vector3(0.1f, 4, 10), wall);
        Box("WallWest", room, new Vector3(-5.05f, 2, 0), new Vector3(0.1f, 4, 10), wall);
        Box("WallNorthLeft", room, new Vector3(-3.5f, 2, 5.05f), new Vector3(3, 4, 0.1f), wall);
        Box("WallNorthRight", room, new Vector3(3.5f, 2, 5.05f), new Vector3(3, 4, 0.1f), wall);
        Box("WallNorthBelow", room, new Vector3(0, 0.4f, 5.05f), new Vector3(4, 0.8f, 0.1f), wall);
        Box("WallNorthAbove", room, new Vector3(0, 3.7f, 5.05f), new Vector3(4, 0.6f, 0.1f), wall);
        var g = Box("WindowGlass", room, new Vector3(0, 2.1f, 5.05f), new Vector3(4, 2.6f, 0.02f), glass);
        Object.DestroyImmediate(g.GetComponent<Collider>());
        Box("WindowCollider", room, new Vector3(0, 2.1f, 5.05f), new Vector3(4, 2.6f, 0.1f), null).GetComponent<Renderer>().enabled = false;
        // neon trim around the window and along the floor
        Box("NeonSill", room, new Vector3(0, 0.79f, 4.98f), new Vector3(4.1f, 0.04f, 0.04f), neon);
        Box("NeonHead", room, new Vector3(0, 3.41f, 4.98f), new Vector3(4.1f, 0.04f, 0.04f), neon);
        Box("NeonJambL", room, new Vector3(-2.03f, 2.1f, 4.98f), new Vector3(0.04f, 2.66f, 0.04f), neon);
        Box("NeonJambR", room, new Vector3(2.03f, 2.1f, 4.98f), new Vector3(0.04f, 2.66f, 0.04f), neon);
        foreach (var (n, p, s) in new[] {
            ("NeonBaseS", new Vector3(0, 0.02f, -4.98f), new Vector3(10, 0.04f, 0.04f)),
            ("NeonBaseE", new Vector3(4.98f, 0.02f, 0), new Vector3(0.04f, 0.04f, 10)),
            ("NeonBaseW", new Vector3(-4.98f, 0.02f, 0), new Vector3(0.04f, 0.04f, 10)) })
            Object.DestroyImmediate(Box(n, room, p, s, neon).GetComponent<Collider>());

        // the sun shines in through the window, slightly from the east
        var sun = new GameObject("Sun").AddComponent<Light>();
        sun.type = LightType.Directional;
        sun.color = new Color(1f, 0.96f, 0.88f);
        sun.intensity = 1.2f;
        sun.shadows = LightShadows.Soft;
        sun.transform.rotation = Quaternion.Euler(35, 200, 0);
        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
        RenderSettings.ambientLight = new Color(0.22f, 0.22f, 0.26f);
        var sh = new UnityEngine.Rendering.SphericalHarmonicsL2();   // batchmode never bakes the ambient probe itself
        sh.AddAmbientLight(RenderSettings.ambientLight);
        RenderSettings.ambientProbe = sh;
        // a soft room light so the gears read from the room side, not only as a silhouette against the sky
        var fill = new GameObject("RoomLight").AddComponent<Light>();
        fill.type = LightType.Point;
        fill.color = new Color(1f, 0.9f, 0.95f);
        fill.range = 12;
        fill.intensity = 0.8f;
        fill.shadows = LightShadows.None;
        fill.transform.position = new Vector3(0, 3.5f, 1.5f);
    }

    static GameObject Box(string name, Transform parent, Vector3 pos, Vector3 size, Material mat)
    {
        var b = GameObject.CreatePrimitive(PrimitiveType.Cube);
        b.name = name;
        b.transform.SetParent(parent, false);
        b.transform.localPosition = pos;
        b.transform.localScale = size;
        if (mat) b.GetComponent<Renderer>().sharedMaterial = mat;
        GameObjectUtility.SetStaticEditorFlags(b, StaticEditorFlags.ContributeGI | StaticEditorFlags.BatchingStatic | StaticEditorFlags.OccluderStatic | StaticEditorFlags.OccludeeStatic);
        return b;
    }

    // ---------- the Rainbow Maker on the glass ----------
    static GameObject PlaceMaker()
    {
        var model = AssetDatabase.LoadAssetAtPath<GameObject>(Fbx);
        var maker = (GameObject)PrefabUtility.InstantiatePrefab(model);
        maker.name = "RainbowMaker";
        maker.transform.localScale = Vector3.one * MakerScale;
        // The FBX root arrives lying down (Blender's up is the model's local +Z, its front local -Y), so stand it up
        // and turn its front into the room (-Z). The suction cup (0.108 m behind the root) touches the glass at z 5.04.
        maker.transform.rotation = Quaternion.Euler(-90, 180, 0);
        maker.transform.position = new Vector3(0, 2.2f, 4.93f);
        var anim = maker.GetComponent<Animator>();   // not ??: Unity's missing components are "fake null"
        if (anim == null) anim = maker.AddComponent<Animator>();
        anim.runtimeAnimatorController = AssetDatabase.LoadAssetAtPath<AnimatorController>(Controller);
        anim.cullingMode = AnimatorCullingMode.CullCompletely;
        var rs = maker.GetComponentsInChildren<Renderer>();
        var b = rs[0].bounds;
        foreach (var r in rs) b.Encapsulate(r.bounds);
        Debug.Log("TheRainbowMakerScene: maker bounds " + b.center.ToString("F3") + " size " + b.size.ToString("F3")
                  + " renderers " + rs.Length + " root scale " + maker.transform.localScale
                  + " crystal " + maker.GetComponentsInChildren<Transform>().First(t => t.name == "crystal").position.ToString("F3")
                  + " panel " + maker.GetComponentsInChildren<Transform>().First(t => t.name == "solar_panel").position.ToString("F3")
                  + " front " + maker.GetComponentsInChildren<Transform>().First(t => t.name == "housing_disc_front").position.ToString("F3"));
        return maker;
    }

    // Six narrow spot lights, one per rainbow colour, ride the crystal shaft so the colours sweep the room as it turns.
    static void AddRainbowLights(GameObject maker)
    {
        var crystal = maker.GetComponentsInChildren<Transform>().First(t => t.name == "crystal");
        var shaft = maker.GetComponentsInChildren<Transform>().First(t => t.name == "crystal_shaft");
        Color[] rainbow = { new Color(1, 0.1f, 0.1f), new Color(1, 0.5f, 0), new Color(1, 0.95f, 0.1f),
                            new Color(0.1f, 1, 0.2f), new Color(0.1f, 0.4f, 1), new Color(0.6f, 0.15f, 1) };
        for (int i = 0; i < rainbow.Length; i++)
        {
            var l = new GameObject("rainbow_" + i).AddComponent<Light>();
            l.type = LightType.Spot;
            l.color = rainbow[i];
            l.spotAngle = 9;
            l.innerSpotAngle = 4;
            l.range = 14;
            l.intensity = 6f;
            l.shadows = LightShadows.None;
            l.renderMode = LightRenderMode.ForcePixel;
            l.transform.position = crystal.position;
            // fan the colours side by side (like a prism's spread), all thrown back into the room
            l.transform.rotation = Quaternion.Euler(14 + i * 1.6f, 180 + 25 + i * 2.2f, 0);
            l.transform.SetParent(shaft, true);
        }
    }

    static void PlaceSpawn()
    {
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(WorldPrefab);
        GameObject world = prefab ? (GameObject)PrefabUtility.InstantiatePrefab(prefab) : new GameObject("VRCWorld");
        world.transform.position = new Vector3(0, 0, -2.5f);
        world.transform.rotation = Quaternion.identity;   // facing +Z, the window
    }

    // ---------- check pictures for Review/ ----------
    static void Snapshot(GameObject maker)
    {
        if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null) return;
        Directory.CreateDirectory("Review");
        var clip = Clip();
        var camGo = new GameObject("snapshot");
        var cam = camGo.AddComponent<Camera>();
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = new Color(0.55f, 0.75f, 0.95f);
        var shots = new[] {
            ("room", new Vector3(0, 1.6f, -2.5f), new Vector3(0, 2f, 5f), 60f, 0f),
            ("closeup-a", new Vector3(0.25f, 2.0f, 3.2f), new Vector3(0, 2.05f, 4.9f), 45f, 0f),
            ("closeup-b", new Vector3(0.25f, 2.0f, 3.2f), new Vector3(0, 2.05f, 4.9f), 45f, 0.5f) };
        foreach (var (n, pos, look, fov, t) in shots)
        {
            clip.SampleAnimation(maker, t);
            var rs = maker.GetComponentsInChildren<Renderer>();
            var b = rs[0].bounds;
            foreach (var r in rs) b.Encapsulate(r.bounds);
            Debug.Log("TheRainbowMakerScene: snapshot " + n + " bounds " + b.center.ToString("F3") + " size " + b.size.ToString("F3")
                      + " first " + rs[0].name + " enabled " + rs[0].enabled + " shader " + rs[0].sharedMaterial?.shader?.name
                      + " layer " + rs[0].gameObject.layer + " active " + rs[0].gameObject.activeInHierarchy);
            cam.transform.position = pos;
            cam.transform.LookAt(look);
            cam.fieldOfView = fov;
            var rt = new RenderTexture(1280, 720, 24) { antiAliasing = 4 };
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(1280, 720, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, 1280, 720), 0, 0);
            File.WriteAllBytes("Review/scene-check-" + n + "-20261022.png", tex.EncodeToPNG());
            RenderTexture.active = null;
            cam.targetTexture = null;
            Object.DestroyImmediate(rt);
        }
        clip.SampleAnimation(maker, 0);
        Object.DestroyImmediate(camGo);
    }
}
