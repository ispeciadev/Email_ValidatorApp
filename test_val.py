import sys
sys.path.insert(0, 'backend')
from validator.multi_layer_check import multi_layer_validate
import time

emails = [
    'test@gmail.com',
    'fake12345@gmail.com',
    'support@example.com',
    'admin@realdomain.com'
]

print('='*60)
print('EMAIL VALIDATION TEST')
print('='*60)

tottime = 0
smchecked = 0

for em in emails:
    t0 = time.time()
    r = multi_layer_validate(em)
    t1 = time.time() - t0
    tottime += t1
    
    print(f'Email: {em}')
    print(f' Status: {r[\"status\"]} - {r[\"reason\"]}')
    print(f' Free: {r[\"is_free_email\"]}')
    smchk = r['smtp_status'] != 'not_checked'
    print(f' SMTP: {smchk}')
    print(f' Time: {t1:.3f}s')
    print()
    if smchk:
        smchecked += 1

print('='*60)
print(f'Avg time: {tottime/len(emails):.3f}s')
print(f'SMTP usage: {smchecked}/{len(emails)} ({100*smchecked/len(emails):.0f}%)')
print('='*60)
