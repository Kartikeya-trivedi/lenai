import requests, time
print('Submitting...')
res = requests.post('https://mindrix--lenai-platform-api-gateway.modal.run/v1/infer/image', data={'prompt': 'A cute cat'}, headers={'X-API-Key': 'dummy'})
jid = res.json()['job_id']
print('Job:', jid)
t0 = time.time()
while True:
    time.sleep(1.5)
    poll = requests.get(f'https://mindrix--lenai-platform-api-gateway.modal.run/v1/jobs/{jid}', headers={'X-API-Key':'dummy'}).json()
    status = poll.get('status')
    print(f'{time.time()-t0:.1f}s: {status}')
    if status in ['completed','failed']:
        break
print('Final URL length:', len(poll.get('output_url', '')))
