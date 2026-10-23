// Spawned by world-spawn-tool (20261022). The agent queue from Astra's Infinite Pole (AstraAgentQueue.cs, 2026-09-24):
// agents drive the Unity editor that is already open instead of relaunching it, so the VRChat SDK sign-in survives.
//
// Write Review/agent-queue/<anything>.cmd whose first line is one of:
//   status                      -> signed-in SDK account, scene, compile/play state
//   refresh                     -> AssetDatabase.Refresh (compiles new scripts)
//   save                        -> saves open scenes
//   menu TheRainbowMaker/<path>    -> runs one of this project's TheRainbowMaker/ menu items (nothing else is allowed)
// The result goes to Review/agent-queue/<same name>.result.txt and the .cmd file is deleted.
// Building, desktop tests and uploads are not wired here yet; uploads always need the owner's OK in chat.
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class TheRainbowMakerAgentQueue
{
    const string Dir = "Review/agent-queue";
    static double nextCheck;

    static TheRainbowMakerAgentQueue()
    {
        if (Application.isBatchMode) return;
        Directory.CreateDirectory(Dir);
        EditorApplication.update += Poll;
        File.WriteAllText(Path.Combine(Dir, "_listener.txt"),
            "Listening since " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " (Unity " + Application.unityVersion + ")\n");
    }

    static void Poll()
    {
        if (EditorApplication.timeSinceStartup < nextCheck) return;
        nextCheck = EditorApplication.timeSinceStartup + 2;
        if (EditorApplication.isCompiling || EditorApplication.isUpdating || EditorApplication.isPlayingOrWillChangePlaymode) return;
        string file;
        try { file = Directory.GetFiles(Dir, "*.cmd").OrderBy(File.GetCreationTimeUtc).FirstOrDefault(); }
        catch { return; }
        if (file == null) return;

        string command, result;
        try { command = (File.ReadLines(file).FirstOrDefault() ?? "").Trim(); File.Delete(file); }
        catch (Exception e) { Write(file, "Could not read command: " + e.Message); return; }
        try { result = Run(command); }
        catch (Exception e) { result = "FAILED: " + e.Message; Debug.LogException(e); }
        Write(file, DateTime.Now.ToString("HH:mm:ss") + " " + command + "\n" + result);
    }

    static void Write(string cmdFile, string text) =>
        File.WriteAllText(Path.ChangeExtension(cmdFile, null) + ".result.txt", text + "\n");

    static string Run(string command)
    {
        var parts = command.Split(new[] { ' ' }, 2);
        var verb = parts[0].ToLowerInvariant();
        var arg = parts.Length > 1 ? parts[1].Trim() : "";
        switch (verb)
        {
            case "status": return Status();
            case "refresh": AssetDatabase.Refresh(); return "Refreshed. Check status again after compiling finishes.";
            case "save": EditorSceneManager.SaveOpenScenes(); return "Saved open scenes.";
            case "menu":
                if (!arg.StartsWith("TheRainbowMaker/")) return "REFUSED: only TheRainbowMaker/ menu items can be run from the queue.";
                EditorSceneManager.SaveOpenScenes();
                return EditorApplication.ExecuteMenuItem(arg) ? "Ran " + arg + ". See its own Review/ report." : "FAILED: no menu item " + arg;
            default: return "Unknown command. Use: status, refresh, save, menu TheRainbowMaker/...";
        }
    }

    static string Status()
    {
        // VRC.Core.APIUser.CurrentUser, looked up by name so this compiles with or without the SDK.
        var apiUser = AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetType("VRC.Core.APIUser")).FirstOrDefault(t => t != null);
        var user = apiUser?.GetProperty("CurrentUser")?.GetValue(null);
        var name = user == null ? (apiUser == null ? "SDK not loaded" : "NOT SIGNED IN") : apiUser.GetProperty("displayName")?.GetValue(user) as string;
        var scene = EditorSceneManager.GetActiveScene();
        return "SDK account: " + name +
               "\nScene: " + scene.path + (scene.isDirty ? " (unsaved changes)" : "") +
               "\nCompiling: " + EditorApplication.isCompiling + ", Play mode: " + EditorApplication.isPlaying;
    }
}
