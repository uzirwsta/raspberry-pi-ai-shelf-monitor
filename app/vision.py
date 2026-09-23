import time
from collections import Counter

import cv2
import numpy as np

from .config import settings
from . import store


class ShelfMonitor:
    """Camera worker. YOLO detections are counted inside configured shelf ROIs.

    Stock is estimated from detections relative to shelf capacity. The confirmation
    buffer prevents a single missed/extra detection from creating a stock event.
    Train a detector with the exact product labels listed in SHELF_PRODUCTS.
    """
    def __init__(self):
        self.lock = __import__("threading").RLock()
        self.frame = None
        self.status = "Starting"
        self.started_at = None
        self.cap = None
        self.model = None
        self.detected = [[] for _ in range(4)]
        self.candidates = [Counter() for _ in range(4)]
        self.wrong_active = [None for _ in range(4)]
        self.demo_tick = 0

    def start(self):
        import threading
        threading.Thread(target=self.run, daemon=True, name="shelf-camera").start()

    def run(self):
        if settings.mode == "camera":
            self.cap = cv2.VideoCapture(settings.camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.height)
            if not self.cap.isOpened():
                self.status = "Camera unavailable — check connection and SHELF_CAMERA_INDEX"
                return
        if settings.model_path:
            try:
                from ultralytics import YOLO
                self.model = YOLO(settings.model_path)
            except Exception as exc:
                self.status = f"Model failed to load: {exc}"
        self.status = "Demo mode · simulated stock changes" if settings.mode == "demo" else "Monitoring · camera connected"
        self.started_at = time.time()
        while True:
            if settings.mode == "demo":
                frame = self.demo_frame()
                self.demo_tick += 1
                if self.demo_tick % max(1, settings.demo_interval * settings.fps) == 0:
                    shelf = ((self.demo_tick // max(1, settings.demo_interval * settings.fps)) - 1) % 4 + 1
                    old = store.shelves()[shelf-1]["quantity"]
                    new = max(0, min(12, old + (1 if (self.demo_tick // settings.fps) % 2 else -1)))
                    typ = "Stock Replenished" if new > old else "Stock Removed"
                    store.update_shelf(shelf, new, frame, typ, "Demo event")
                    self.draw(frame)
            else:
                ok, frame = self.cap.read()
                if not ok:
                    self.status = "Camera stream interrupted · reconnecting"
                    time.sleep(1)
                    continue
                if self.model:
                    self.infer(frame)
                self.draw(frame)
            with self.lock:
                self.frame = frame
            time.sleep(1 / max(settings.fps, 1))

    def infer(self, frame):
        result = self.model(frame, verbose=False)[0]
        names = self.model.names
        present = [Counter() for _ in range(4)]
        boxes = []
        for box in result.boxes:
            x1,y1,x2,y2 = map(int, box.xyxy[0].tolist())
            cls = int(box.cls[0]); label = str(names[cls])
            cx,cy=(x1+x2)//2,(y1+y2)//2
            for i, (rx,ry,rw,rh) in enumerate(settings.regions[:4]):
                x,y,w,h=int(rx*frame.shape[1]),int(ry*frame.shape[0]),int(rw*frame.shape[1]),int(rh*frame.shape[0])
                if x <= cx <= x+w and y <= cy <= y+h:
                    present[i][label] += 1
                    boxes.append((x1,y1,x2,y2,label,i+1))
                    break
        self.detected = [[(b[0],b[1],b[2],b[3],b[4]) for b in boxes if b[5] == i+1] for i in range(4)]
        current = store.shelves()
        for i, counts in enumerate(present):
            expected = settings.products[i]
            wrong_counts = {name:n for name,n in counts.items() if name.casefold() != expected.casefold()}
            wrong = max(wrong_counts, key=wrong_counts.get) if wrong_counts else None
            if wrong:
                buf = self.candidates[i]
                for candidate in list(buf):
                    if candidate.startswith("wrong:") and candidate != f"wrong:{wrong}":
                        buf[candidate] = 0
                buf[f"wrong:{wrong}"] += 1
                if buf[f"wrong:{wrong}"] >= settings.confirm_frames and self.wrong_active[i] != wrong:
                    assigned = next((j+1 for j,p in enumerate(settings.products) if p.casefold() == wrong.casefold()), "unknown")
                    store.update_shelf(i+1, current[i]["quantity"], frame, "WRONG SHELF", f"{wrong} detected · assigned shelf {assigned}", current[i]["product"])
                    self.wrong_active[i] = wrong
                if not counts.get(expected):
                    continue  # misplaced stock does not count toward the assigned product
            else:
                for candidate in list(self.candidates[i]):
                    if candidate.startswith("wrong:"):
                        self.candidates[i][candidate] = 0
                self.wrong_active[i] = None
            quantity = counts.get(expected, 0)
            self.confirm(i, str(quantity), min(quantity, current[i]["capacity"]), frame, None, None, expected)

    def confirm(self, i, key, quantity, frame, forced_event=None, detail=None, product=None):
        buf=self.candidates[i]
        for candidate in list(buf):
            if candidate != key:
                buf[candidate] = 0
        buf[key]+=1
        if buf[key] < settings.confirm_frames:
            return
        for other in list(buf):
            if other != key: buf[other]=0
        shelf=store.shelves()[i]; previous=shelf["quantity"]
        changed = quantity != previous or (product and product != shelf["product"])
        if not changed and not forced_event: return
        event=forced_event
        if not event and quantity != previous:
            event = "Stock Replenished" if quantity > previous else "Stock Removed"
        if not event and product != shelf["product"]: event="Product Changed"
        level = self.level(quantity, shelf["capacity"])
        # Save a screenshot when stock changes or crosses an important state.
        if event or level == "Empty":
            store.update_shelf(i+1, quantity, frame, event, detail, product)
        else:
            store.update_shelf(i+1, quantity, None, None, None, product)
        buf.clear()

    @staticmethod
    def level(q, capacity):
        if q == 0: return "Empty"
        ratio=q/max(capacity,1)
        return "Low" if ratio <= .25 else "Medium" if ratio <= .65 else "Full"

    def demo_frame(self):
        h,w=settings.height,settings.width
        frame=np.full((h,w,3),(18,25,33),dtype=np.uint8)
        for i, shelf in enumerate(store.shelves()):
            x,y,rw,rh=settings.regions[i]; x,y,rw,rh=int(x*w),int(y*h),int(rw*w),int(rh*h)
            cv2.rectangle(frame,(x,y),(x+rw,y+rh),(53,69,82),2)
            q=shelf["quantity"]
            for n in range(q):
                col=n%6; row=n//6
                px=x+16+col*(rw-28)//6; py=y+62+row*92
                color=[(56,133,232),(198,87,75),(63,169,121),(208,144,66)][i]
                cv2.rectangle(frame,(px,py),(px+38,py+66),color,-1)
                cv2.rectangle(frame,(px+4,py+12),(px+34,py+46),(236,239,239),-1)
                cv2.putText(frame,shelf["product"][:3].upper(),(px+5,py+34),cv2.FONT_HERSHEY_SIMPLEX,.27,(40,46,50),1)
        return frame

    def draw(self, frame):
        for i,(rx,ry,rw,rh) in enumerate(settings.regions[:4]):
            x,y,w,h=int(rx*frame.shape[1]),int(ry*frame.shape[0]),int(rw*frame.shape[1]),int(rh*frame.shape[0])
            cv2.rectangle(frame,(x,y),(x+w,y+h),(58,198,155),2)
            cv2.putText(frame,f"SHELF {i+1}  {settings.products[i]}",(x+9,y+23),cv2.FONT_HERSHEY_SIMPLEX,.6,(231,246,241),2)
            for x1,y1,x2,y2,label in self.detected[i]:
                cv2.rectangle(frame,(x1,y1),(x2,y2),(249,186,83),2)
                cv2.putText(frame,label,(x1,y1-7),cv2.FONT_HERSHEY_SIMPLEX,.5,(249,186,83),1)

    def jpeg(self):
        with self.lock:
            if self.frame is None:
                return None
            return cv2.imencode(".jpg",self.frame,[cv2.IMWRITE_JPEG_QUALITY,78])[1].tobytes()
