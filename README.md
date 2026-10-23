# The Rainbow Maker

a VRChat world around a solar Rainbow Maker: watch its tiny gear train turn and spin a crystal that throws rainbows across the room.

## Working in it

- Unity 2022.3.22f1, started fresh from VRChat Creator Companion's World template 1.5.0, with the VRChat SDK (com.vrchat.base 3.10.5, com.vrchat.worlds 3.10.5) unpacked from VCC's package cache into `Packages/` (not committed). Spawned with world-spawn-tool 0.2.0-20261019 on 20261022; nothing in it came from another world.
- Agents drive an open editor through `Review/agent-queue/*.cmd` (`status`, `refresh`, `save`, `menu TheRainbowMaker/...`). Never relaunch or batchmode Unity while the project is open.
- A piece from another world comes in only when Astra names it.
- Uploads, releases and `main` change only with Astra's OK.
