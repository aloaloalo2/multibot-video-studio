"""Durable FIFO of author-requested frame edits. Never retries a paid run."""
import threading
import time
import uuid

import production
import store

LOCK=threading.RLock()


def path(pid):
    return store.project_dir(pid)/'production-edits.json'


def read(pid):
    value=store.read_json(path(pid),[])
    return value if isinstance(value,list) else []


def overview(pid):
    with LOCK:
        jobs=read(pid)
        return {'jobs':jobs,'queued':sum(j['status']=='queued' for j in jobs)}


def enqueue(pid,notes,frame_numbers,client_id):
    if not isinstance(notes,str) or not notes.strip() or len(notes)>4000:
        raise store.StudioError('Опишіть правки, до 4000 знаків',400)
    if not isinstance(client_id,str) or not 8<=len(client_id)<=80:
        raise store.StudioError('Потрібен ідентифікатор запиту',400)
    with LOCK:
        jobs=read(pid)
        project=store.load_project(pid)
        selected=production.validate_repair_frames(pid,project.get('production_request') or {},frame_numbers)
        previous=next((j for j in jobs if j.get('client_id')==client_id),None)
        if previous:
            if previous['notes']!=notes.strip() or previous['frame_numbers']!=selected:
                raise store.StudioError('Цей запит уже збережено з іншими правками. Відкрийте новий запит.',409)
            return overview(pid)
        if sum(j['status']=='queued' for j in jobs)>=100:
            raise store.StudioError('У черзі вже 100 запитів',409)
        jobs.append({'id':uuid.uuid4().hex[:16],'client_id':client_id,'notes':notes.strip(),
                     'frame_numbers':selected,'status':'queued','created_at':time.time()})
        store.atomic_json(path(pid),jobs)
        return overview(pid)


def cancel(pid,jid):
    with LOCK:
        jobs=read(pid)
        job=next((j for j in jobs if j['id']==jid),None)
        if not job:raise store.StudioError('Запит не знайдено',404)
        if job['status']!='queued':raise store.StudioError('Можна прибрати лише правки, які ще чекають',409)
        job.update(status='cancelled',finished_at=time.time())
        store.atomic_json(path(pid),jobs)
        return overview(pid)


def tick(blocked=()):
    """Called under the server restart/mutation gate, once native workers are registered."""
    with LOCK:
        for file in (store.DATA_ROOT/'projects').glob('*/production-edits.json'):
            pid=file.parent.name
            jobs=read(pid)
            if not any(j['status'] in {'queued','starting','running'} for j in jobs):continue
            if pid in production.ACTIVE:continue
            try:request=store.load_project(pid).get('production_request') or {}
            except store.StudioError:continue
            changed=False
            for job in jobs:
                if job['status'] not in {'starting','running'}:continue
                same=(request.get('id')==job.get('request_id') and request.get('fixes')==job.get('fixes')
                      and request.get('notes')==job['notes'] and request.get('repair_frames')==job['frame_numbers'])
                if same and request.get('status') in {'requested','in_progress'}:break
                job.update(status='done' if same and request.get('status')=='done' else 'failed',finished_at=time.time())
                if job['status']=='failed':job['error']=request.get('error') if same else 'Початок правок не підтверджено. Автоматичного платного повтору немає.'
                changed=True
            else:
                if pid not in blocked and request.get('status') in {'done','failed'} and not (request.get('paused') or request.get('limit')):
                    job=next((j for j in jobs if j['status']=='queued'),None)
                    if job:
                        job.update(status='starting',started_at=time.time(),request_id=request['id'],fixes=int(request.get('fixes') or 0)+1)
                        store.atomic_json(file,jobs)
                        try:
                            production.fix(pid,job['notes'],frame_numbers=job['frame_numbers'])
                            job['status']='running'
                        except (OSError,store.StudioError) as error:
                            job.update(status='failed',error=str(error),finished_at=time.time())
                        changed=True
            if changed:store.atomic_json(file,jobs)
