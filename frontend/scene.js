// Animated orb scene using Three.js
// Responds to voice via WebAudio analyser node

let scene, camera, renderer, orb, analyser, dataArray;

export async function setupScene() {
    // Load Three.js from CDN
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
    script.async = true;

    return new Promise((resolve, reject) => {
        script.onload = () => {
            try {
                initScene();
                resolve();
            } catch (e) {
                reject(e);
            }
        };
        script.onerror = reject;
        document.head.appendChild(script);
    });
}

function initScene() {
    const canvas = document.getElementById('orbCanvas');

    // Three.js setup
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);

    camera = new THREE.PerspectiveCamera(
        75,
        canvas.clientWidth / canvas.clientHeight,
        0.1,
        1000
    );
    camera.position.z = 3;

    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
    renderer.setPixelRatio(window.devicePixelRatio || 1);

    // Create orb geometry
    const geometry = new THREE.IcosahedronGeometry(1.5, 5);
    const material = new THREE.MeshPhongMaterial({
        color: 0x00d4ff,
        emissive: 0x00aa99,
        shininess: 100,
        wireframe: false,
    });
    orb = new THREE.Mesh(geometry, material);
    scene.add(orb);

    // Lighting
    const light = new THREE.PointLight(0xffffff, 1);
    light.position.set(5, 5, 5);
    scene.add(light);

    const ambientLight = new THREE.AmbientLight(0x444444);
    scene.add(ambientLight);

    // WebAudio analyser for voice reactivity
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    dataArray = new Uint8Array(analyser.frequencyBinCount);

    window.audioContext = audioCtx;
    window.analyser = analyser;

    // Handle window resize
    window.addEventListener('resize', onWindowResize);

    // Animation loop
    function animate() {
        requestAnimationFrame(animate);

        // Slow base rotation
        orb.rotation.x += 0.0002;
        orb.rotation.y += 0.0003;

        // Voice-reactive scale (analyser data)
        try {
            analyser.getByteFrequencyData(dataArray);
            const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
            const scale = 1 + (average / 255) * 0.3; // Scale 1.0 to 1.3 based on volume
            orb.scale.set(scale, scale, scale);
        } catch (e) {
            // Analyser may not be connected yet; ignore
        }

        renderer.render(scene, camera);
    }

    animate();
}

function onWindowResize() {
    const canvas = document.getElementById('orbCanvas');
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;

    camera.aspect = width / height;
    camera.updateProjectionMatrix();

    renderer.setSize(width, height, false);
}

export function getAudioContext() {
    return window.audioContext;
}

export function getAnalyser() {
    return window.analyser;
}
