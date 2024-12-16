import os

m = 1
for entry in os.listdir('entries/'):
    n = 1
    
    for image in os.listdir(f'entries/{entry}/'):
        os.rename(f'entries/{entry}/{image}', f'entries/{entry}/{n}.jpg')
        n += 1
        
    os.rename(f'entries/{entry}', f'entries/PACK_{m}')
    m += 1
    