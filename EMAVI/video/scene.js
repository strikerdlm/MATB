import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
export const defaults = { deskWidth: 1.8, deskDepth: .82, monitorWidth: .76, droneSpan: .52 };
// Illustrative metres, +Y up. No measured product dimensions or physiological model.
export function createStation(host, p = defaults) {
    for (const value of Object.values(p))
        if (!Number.isFinite(value) || value <= 0 || value > 4)
            throw new Error('Invalid illustrative dimension');
    if (p.deskWidth < 1 || p.deskDepth < .5 || p.monitorWidth < .3 || p.monitorWidth > p.deskWidth - .3 || p.droneSpan < .2)
        throw new Error('Incompatible illustrative dimensions');
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#07111f');
    const camera = new THREE.PerspectiveCamera(35, 1, .05, 40);
    camera.position.set(2.8, 2.25, 3.7);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    host.append(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, .65, 0);
    controls.enableDamping = false;
    controls.minDistance = 1.5;
    controls.maxDistance = 7;
    controls.maxPolarAngle = Math.PI * .48;
    scene.add(new THREE.HemisphereLight(0xb1dcff, 0x182238, 3));
    const key = new THREE.DirectionalLight(0xffffff, 4);
    key.position.set(2, 5, 3);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x46dadd, 3);
    rim.position.set(-4, 2, -3);
    scene.add(rim);
    const root = new THREE.Group();
    scene.add(root);
    const parts = new Map();
    const mats = { dark: new THREE.MeshStandardMaterial({ color: 0x192b42, metalness: .6, roughness: .32 }), silver: new THREE.MeshStandardMaterial({ color: 0x8c9ba9, metalness: .75, roughness: .3 }), gold: new THREE.MeshStandardMaterial({ color: 0xe6bb69, metalness: .6, roughness: .33 }), screen: new THREE.MeshStandardMaterial({ color: 0x0b2432, emissive: 0x103b4c, emissiveIntensity: .6 }), cyan: new THREE.MeshStandardMaterial({ color: 0x46dadd, emissive: 0x167c94, emissiveIntensity: .3 }) };
    function part(id, x, y, z) { const g = new THREE.Group(); g.name = id; g.position.set(x, y, z); root.add(g); parts.set(id, g); return g; }
    function box(g, w, h, d, x, y, z, m) { const o = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); o.position.set(x, y, z); g.add(o); return o; }
    function cyl(g, r, h, x, y, z, m) { const o = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 24), m); o.position.set(x, y, z); g.add(o); return o; }
    const desk = part('station', 0, .48, 0);
    box(desk, p.deskWidth, .07, p.deskDepth, 0, 0, 0, mats.dark);
    for (const x of [-.73, .73])
        for (const z of [-.29, .29])
            box(desk, .04, .48, .04, x, -.27, z, mats.silver);
    const monitor = part('monitor', -.12, .83, -.20);
    box(monitor, p.monitorWidth, .45, .045, 0, .13, 0, mats.dark);
    box(monitor, p.monitorWidth - .045, .405, .008, 0, .13, .027, mats.screen);
    box(monitor, .06, .24, .05, 0, -.17, 0, mats.silver);
    box(monitor, .26, .025, .18, 0, -.30, .015, mats.silver);
    for (let row = 0; row < 2; row++)
        for (let col = 0; col < 2; col++) {
            box(monitor, .32, .166, .006, (col - .5) * .354, .13 + (row - .5) * .187, .036, mats.dark);
            for (let k = 0; k < 4; k++)
                box(monitor, .21 - k * .029, .006, .007, (col - .5) * .354, .14 + (row - .5) * .187 + k * .024, .044, k === 0 ? mats.gold : mats.cyan);
        }
    const keyboard = part('keyboard', -.13, .535, .25);
    box(keyboard, .57, .025, .18, 0, 0, 0, mats.silver);
    for (let r = 0; r < 4; r++)
        for (let c = 0; c < 13; c++)
            box(keyboard, .032, .011, .028, (c - 6) * .039, .018, (r - 1.5) * .037, mats.dark);
    const joystick = part('controller', .61, .54, .22);
    box(joystick, .21, .036, .22, 0, 0, 0, mats.dark);
    cyl(joystick, .027, .15, 0, .09, 0, mats.silver);
    const grip = cyl(joystick, .038, .095, 0, .21, 0, mats.dark);
    grip.rotation.z = -.15;
    box(joystick, .02, .012, .027, .018, .263, .018, mats.gold);
    const sensor = part('sensor', -.69, .56, .20);
    const band = new THREE.Mesh(new THREE.TorusGeometry(.093, .011, 10, 40), mats.dark);
    band.rotation.x = Math.PI / 2;
    band.scale.set(1.25, 1, 1);
    sensor.add(band);
    box(sensor, .085, .03, .04, 0, .018, .079, mats.silver);
    box(sensor, .024, .008, .012, 0, .037, .079, mats.cyan);
    const drone = part('aircraft', .88, 1.32, -.2);
    box(drone, .16, .055, .11, 0, 0, 0, mats.silver);
    const rotors = [];
    for (const x of [-1, 1])
        for (const z of [-1, 1]) {
            const a = box(drone, p.droneSpan * .63, .024, .024, x * p.droneSpan * .19, 0, z * p.droneSpan * .19, mats.dark);
            a.rotation.y = -x * z * Math.PI / 4;
            const px = x * p.droneSpan * .36, pz = z * p.droneSpan * .36;
            cyl(drone, .026, .045, px, .028, pz, mats.gold);
            const rotor = new THREE.Group();
            rotor.position.set(px, .059, pz);
            drone.add(rotor);
            box(rotor, .20, .005, .016, 0, 0, 0, mats.cyan);
            rotors.push(rotor);
        }
    const floor = new THREE.GridHelper(5, 30, 0x275768, 0x172c40);
    scene.add(floor);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.2, .006, 8, 100), mats.gold);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = .014;
    scene.add(ring);
    const assembled = new Map([...parts].map(([id, g]) => [id, g.position.clone()]));
    let explode = 0, playing = !matchMedia('(prefers-reduced-motion: reduce)').matches, time = 0, last = 0, raf = 0, disposed = false;
    const intervals = [];
    function setExplode(value) { explode = THREE.MathUtils.clamp(value, 0, 1); for (const [id, g] of parts) {
        g.position.copy(assembled.get(id));
        if (id !== 'station') {
            const offset = id === 'aircraft' ? new THREE.Vector3(.4, .15, 0) : new THREE.Vector3(g.position.x * .45, .3, g.position.z * .7);
            g.position.addScaledVector(offset, explode);
        }
    } render(); }
    function setTime(t) { time = t; rotors.forEach((r, i) => r.rotation.y = t * 9 * (i % 2 ? 1 : -1)); drone.position.y = assembled.get('aircraft').y + explode * .15 + Math.sin(t * .8) * .03; root.rotation.y = Math.sin(t * .13) * .10; render(); }
    function render() { if (!disposed)
        renderer.render(scene, camera); }
    function resize() { const { width, height } = host.getBoundingClientRect(); renderer.setSize(width, height); camera.aspect = width / Math.max(height, 1); camera.updateProjectionMatrix(); render(); }
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    controls.addEventListener('change', render);
    function tick(now) { if (disposed)
        return; if (last && playing && !document.hidden) {
        const dt = Math.min((now - last) / 1000, .05);
        if (intervals.length < 1000)
            intervals.push(now - last);
        setTime(time + dt);
    } last = now; raf = playing && !document.hidden ? requestAnimationFrame(tick) : 0; }
    function setPlaying(v) { playing = v; last = 0; cancelAnimationFrame(raf); raf = v && !document.hidden ? requestAnimationFrame(tick) : 0; }
    const visibility = () => setPlaying(playing);
    document.addEventListener('visibilitychange', visibility);
    function reset() { setPlaying(false); time = 0; root.rotation.set(0, 0, 0); setExplode(0); setTime(0); camera.position.set(2.8, 2.25, 3.7); controls.target.set(0, .65, 0); controls.update(); render(); }
    resize();
    setPlaying(playing);
    return { setTime, setExplode, setPlaying, reset, parts,
        focus(id) { const g = parts.get(id); if (g) {
            controls.target.copy(g.position);
            controls.update();
            render();
        } },
        metrics() { const sorted = [...intervals].sort((a, b) => a - b); return { three: THREE.REVISION, drawCalls: renderer.info.render.calls, triangles: renderer.info.render.triangles, frames: sorted.length, medianMs: sorted[Math.floor(sorted.length * .5)], p95Ms: sorted[Math.floor(sorted.length * .95)], dpr: renderer.getPixelRatio(), viewport: [host.clientWidth, host.clientHeight], renderer: renderer.getContext().getParameter(renderer.getContext().RENDERER) }; },
        dispose() { disposed = true; cancelAnimationFrame(raf); document.removeEventListener('visibilitychange', visibility); observer.disconnect(); controls.dispose(); const geometries = new Set(), materials = new Set(); scene.traverse(o => { if (o instanceof THREE.Mesh) {
            geometries.add(o.geometry);
            for (const m of Array.isArray(o.material) ? o.material : [o.material])
                materials.add(m);
        } }); geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); floor.geometry.dispose(); floor.material.dispose(); renderer.dispose(); renderer.domElement.remove(); }
    };
}
