import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

/**
 * Draws the GLB at `url` into `canvas`, framed to fit, and returns the function that releases the
 * renderer and the geometry. Loaded lazily by `GeometryPreview`, so three.js stays out of the
 * chat's first bundle.
 */
export async function mountGlbPreview(canvas: HTMLCanvasElement, url: string): Promise<() => void> {
  const { width, height } = canvas.getBoundingClientRect();
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(width, height, false);
  renderer.setClearColor(0x0b1220, 1);

  const gltf = await new GLTFLoader().loadAsync(url);
  const scene = new THREE.Scene();
  scene.add(new THREE.AmbientLight(0xffffff, 1.2), new THREE.DirectionalLight(0xffffff, 1.5));
  scene.add(gltf.scene);
  renderer.render(scene, frameCamera(gltf.scene, width / height));

  return () => {
    renderer.dispose();
    disposeTree(gltf.scene);
  };
}

/** A camera on the +z side of the object, far enough back for its bounding sphere to fit. */
function frameCamera(object: THREE.Object3D, aspect: number): THREE.PerspectiveCamera {
  const box = new THREE.Box3().setFromObject(object);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.x, size.y, size.z, 1e-3) / 2;
  const camera = new THREE.PerspectiveCamera(40, aspect, radius / 100, radius * 100);
  const distance = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2);
  camera.position.copy(center).add(new THREE.Vector3(0, 0, distance * 1.2));
  camera.lookAt(center);
  return camera;
}

function disposeTree(root: THREE.Object3D): void {
  root.traverse((node) => {
    if (node instanceof THREE.Mesh || node instanceof THREE.Points || node instanceof THREE.Line) {
      node.geometry.dispose();
      const materials = Array.isArray(node.material) ? node.material : [node.material];
      for (const material of materials) material.dispose();
    }
  });
}
