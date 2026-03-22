import threading
import time
import uuid

# Struttura della coda globale in memoria.
# Per applicazioni complesse useremmo Redis/Celery, ma per SQLite un array con thread locale è perfetto.
#
# job structure:
# {
#   "job_id": str,
#   "status": "queued" | "running" | "completed" | "error",
#   "progress": int (da 0 a 100 per job di gruppo),
#   "message": str (cosa sta facendo, ultimo capitolo),
#   "result": None,
#   "capitoli": list[int],
#   "provider": str,
#   "model": str
# }

_queue = []
_jobs_history = {}
_worker_running = False
_queue_lock = threading.Lock()

# Abbiamo bisogno di eseguire app.py roba importando da qui o passando closure, 
# per non creare import ciclici. L'app darà un handler callback al worker.
_process_callback = None 

def set_job_callback(callback):
    """
    Callback func signature: callback(cap_id, provider, model, update_status_func) -> bool
    update_status_func(msg) can be called to update the job message.
    """
    global _process_callback
    _process_callback = callback

def update_active_job_message(msg):
    with _queue_lock:
        for job in _queue:
            if job['status'] == 'running':
                job['message'] = msg
                break

def get_job_status(job_id):
    with _queue_lock:
        return _jobs_history.get(job_id)

def get_active_job():
    with _queue_lock:
        for job in _queue:
            if job['status'] in ('queued', 'running'):
                return job
        return None

def enqueue_generation(cap_ids, provider, model, extra_prompt=""):
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "message": f"In coda per {len(cap_ids)} capitoli...",
        "capitoli": cap_ids,
        "provider": provider,
        "model": model,
        "extra_prompt": extra_prompt,
        "totale": len(cap_ids),
        "fatti": 0
    }
    with _queue_lock:
        _queue.append(job)
        _jobs_history[job_id] = job
    
    start_worker()
    return job_id

def worker_thread():
    global _worker_running
    while True:
        job_to_process = None
        
        with _queue_lock:
            for job in _queue:
                if job['status'] == 'queued':
                    job_to_process = job
                    break
            if not job_to_process:
                # Coda vuota
                _worker_running = False
                break
            
            job_to_process['status'] = 'running'
            job_to_process['message'] = "Avvio generazione..."
            
        # Processamento Job
        try:
            for i, cid in enumerate(job_to_process['capitoli']):
                with _queue_lock:
                    job_to_process['progress'] = int((i / job_to_process['totale']) * 100)
                    job_to_process['message'] = f"Generazione Capitolo {cid} ({i+1}/{job_to_process['totale']}) con {job_to_process['model']}..."
                
                # Chiama la logica dal app.py
                if _process_callback:
                    print(f"[Queue] Esecuzione callback per cap {cid}...")
                    _process_callback(cid, job_to_process['provider'], job_to_process['model'], update_active_job_message, extra_prompt=job_to_process.get('extra_prompt', ''))
                else:
                    print(f"[Queue] WARNING: _process_callback non impostata! Mocking cap {cid}...")
                    time.sleep(1) # mock 
                    
                with _queue_lock:
                    job_to_process['fatti'] = i + 1
                    
            with _queue_lock:
                job_to_process['status'] = 'completed'
                job_to_process['progress'] = 100
                job_to_process['message'] = f"Completati {job_to_process['totale']} capitoli."
        except Exception as e:
            with _queue_lock:
                job_to_process['status'] = 'error'
                job_to_process['message'] = f"Errore: {str(e)}"
        finally:
            with _queue_lock:
                if job_to_process in _queue:
                    _queue.remove(job_to_process)


def start_worker():
    global _worker_running
    with _queue_lock:
        if not _worker_running:
            _worker_running = True
            t = threading.Thread(target=worker_thread, daemon=True)
            t.start()
