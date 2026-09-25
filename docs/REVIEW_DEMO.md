# OrchLang Demonstration Script

The demonstration now lives in **[DEMO.md](../DEMO.md)** at the repository
root. It covers the same ground as the sequence that used to be here: build and
test, structural cost bounds, secrets, injection, implicit flow, the cost
channel and the withdrawn equal-bounds rule, the certificate, the front-end
phases, and the evaluation. It is now scripted:

```sh
./demo.sh setup     # once: toolchain, clean build, tests, rehearsal
./demo.sh           # present, one command per key press
./demo.sh check     # verify every command still produces what the script says
```

The talking points are in DEMO.md, section 4, scene by scene.
