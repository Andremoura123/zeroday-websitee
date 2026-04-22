document.addEventListener('DOMContentLoaded', () => {

    if (typeof THREE === 'undefined') {
        console.error('Erro: A biblioteca Three.js não foi carregada.');
        return;
    }

    const container = document.getElementById('zero-day-3d-bg');
    if (!container) {
        console.error('Erro: Contentor #zero-day-3d-bg não encontrado.');
        return;
    }

    let scene, camera, renderer, raycaster, mouse;
    const clickableLEDs = [];
    const digitalSnow = [];
    
    // --- AJUSTE: Neve Mais Forte ---
    const numSnowParticles = 600; // O DOBRO de "flocos"
    
    const numStrands = 100;
    const ledsPerStrand = 40;
    const strandLength = 35;
    const strandWidth = 85;
    const strandDepth = 10; 

    const mouseWorldPosition = new THREE.Vector3();
    const physicsPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0); 
    const radiusOfInfluence = 5.0; 
    const repelForce = 1.2;      
    const springFactor = 0.01;   
    const damping = 0.90;        

    function init() {
        scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2(0x000000, 0.02);

        camera = new THREE.PerspectiveCamera(50, container.clientWidth / container.clientHeight, 0.1, 1000);
        camera.position.z = 25;
        camera.position.y = 5;
        camera.lookAt(scene.position);

        renderer = new THREE.WebGLRenderer({ 
            alpha: true, 
            antialias: true 
        });
        renderer.setSize(container.clientWidth, container.clientHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        container.appendChild(renderer.domElement);

        raycaster = new THREE.Raycaster();
        mouse = new THREE.Vector2();

        // --- Textura de LED Nítido (Usada para TUDO) ---
        function createLedTexture() {
            const canvas = document.createElement('canvas');
            canvas.width = 32;
            canvas.height = 32;
            const context = canvas.getContext('2d');
            context.beginPath();
            context.arc(16, 16, 14, 0, 2 * Math.PI);
            context.fillStyle = 'rgba(255,255,255,1)';
            context.fill();
            return new THREE.CanvasTexture(canvas);
        }
        const ledTexture = createLedTexture();
        
        // --- Materiais da Cortina ---
        const lineMaterial = new THREE.LineBasicMaterial({ color: 0x404040, transparent: true, opacity: 0.1 });
        const ledMaterialGold = new THREE.SpriteMaterial({ map: ledTexture, color: 0xFFD700, blending: THREE.AdditiveBlending, transparent: true, opacity: 0.9, depthWrite: false });
        const ledMaterialWhite = new THREE.SpriteMaterial({ map: ledTexture, color: 0xFFFFFF, blending: THREE.AdditiveBlending, transparent: true, opacity: 0.9, depthWrite: false });
        const ledMaterials = [ledMaterialGold, ledMaterialWhite, ledMaterialGold, ledMaterialGold];

        // --- Materiais da "Neve" (Mais Brilhantes) ---
        const snowMaterialGold = new THREE.SpriteMaterial({
            map: ledTexture, 
            color: 0xDAA520, 
            blending: THREE.AdditiveBlending,
            transparent: true,
            opacity: 0.7, // MAIS BRILHANTE
            depthWrite: false
        });
        const snowMaterialWhite = new THREE.SpriteMaterial({
            map: ledTexture, 
            color: 0xFFFFFF, 
            blending: THREE.AdditiveBlending,
            transparent: true,
            opacity: 0.7, // MAIS BRILHANTE
            depthWrite: false
        });
        const snowMaterials = [snowMaterialGold, snowMaterialWhite];

        // --- Criar as Cortinas de LED ---
        for (let i = 0; i < numStrands; i++) {
            const points = [];
            const xStart = (i / numStrands - 0.5) * strandWidth * 1.5; 
            const zOffset = (Math.random() - 0.5) * strandDepth; 
            const yTop = 15;

            for (let j = 0; j < ledsPerStrand; j++) {
                const y = yTop - (j / ledsPerStrand) * strandLength;
                const x = xStart + Math.sin(j * 0.05 + i) * 0.05; 
                points.push(new THREE.Vector3(x, y, zOffset));
            }

            const geometry = new THREE.BufferGeometry().setFromPoints(points);
            scene.add(new THREE.Line(geometry, lineMaterial));

            for (let j = 0; j < ledsPerStrand; j++) {
                const material = ledMaterials[Math.floor(Math.random() * ledMaterials.length)];
                const led = new THREE.Sprite(material.clone()); 
                led.position.copy(points[j]); 
                const scale = Math.random() * 0.2 + 0.1;
                led.scale.set(scale, scale, scale);
                
                led.userData.originalPosition = led.position.clone();
                led.userData.velocity = new THREE.Vector3(); 
                led.userData.baseColor = led.material.color.getHex();
                led.userData.secretMessage = `LED_Strand_${i+1}_Pos_${j+1}.log`;
                scene.add(led);
                clickableLEDs.push(led);
            }
        }

        // --- Criar a "Neve" de Luzes (Mais Rápida e Maior) ---
        for (let i = 0; i < numSnowParticles; i++) {
            const material = snowMaterials[Math.floor(Math.random() * snowMaterials.length)];
            const snowFlake = new THREE.Sprite(material.clone());

            snowFlake.position.x = (Math.random() - 0.5) * strandWidth * 1.5;
            snowFlake.position.y = Math.random() * 20 + 15; 
            snowFlake.position.z = (Math.random() - 0.5) * strandDepth * 2; 

            // Escala ligeiramente maior
            const scale = Math.random() * 0.15 + 0.05; 
            snowFlake.scale.set(scale, scale, scale);

            // Velocidade de queda MAIS RÁPIDA
            snowFlake.userData.fallSpeed = Math.random() * 0.04 + 0.02;

            scene.add(snowFlake);
            digitalSnow.push(snowFlake);
        }
        // --- Fim da Neve ---

        window.addEventListener('resize', onWindowResize);
        window.addEventListener('mousemove', onMouseMove); 
        container.addEventListener('click', onMouseClick);

        animate();
    }

    function animate() {
        requestAnimationFrame(animate);

        const repelVec = new THREE.Vector3();
        const springVec = new THREE.Vector3();

        // Animação dos LEDs
        clickableLEDs.forEach((led, index) => {
            const blink = Math.abs(Math.sin(Date.now() * 0.003 + index * 0.5));
            led.material.opacity = (blink > 0.6) ? 0.9 : 0.2;
            
            const dist = led.position.distanceTo(mouseWorldPosition);
            if (dist < radiusOfInfluence) {
                const force = (radiusOfInfluence - dist) / radiusOfInfluence;
                repelVec.subVectors(led.position, mouseWorldPosition).normalize();
                led.userData.velocity.add(repelVec.multiplyScalar(force * repelForce));
            }

            springVec.subVectors(led.userData.originalPosition, led.position);
            led.userData.velocity.add(springVec.multiplyScalar(springFactor));
            led.userData.velocity.multiplyScalar(damping);
            led.position.add(led.userData.velocity);
        });

        // --- Animação da "Neve" de Luzes ---
        digitalSnow.forEach(flake => {
            flake.position.y -= flake.userData.fallSpeed;
            
            if (flake.position.y < -20) {
                flake.position.y = 25; 
                flake.position.x = (Math.random() - 0.5) * strandWidth * 1.5; 
            }
        });
        // --- Fim da animação da Neve ---

        renderer.render(scene, camera);
    }

    function onWindowResize() {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    }

    function onMouseMove(event) {
        mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
        
        raycaster.setFromCamera(mouse, camera);
        raycaster.ray.intersectPlane(physicsPlane, mouseWorldPosition);
    }

    function onMouseClick(event) {
        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(clickableLEDs); 

        if (intersects.length > 0) {
            const clickedObject = intersects[0].object;
            alert(clickedObject.userData.secretMessage);
            
            clickedObject.material.color.set(0x00FF00); 
            setTimeout(() => {
                clickedObject.material.color.setHex(clickedObject.userData.baseColor); 
            }, 150);
        }
    }

    init(); 
});