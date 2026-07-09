import subprocess, tempfile, os, shutil

ffmpeg = shutil.which('ffmpeg')
tmpdir = tempfile.mkdtemp()

# Test 1: basic color source
out1 = os.path.join(tmpdir, 'test1.mp4')
r = subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'color=c=0x0a0a2a:s=1280x720:r=30:d=3',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '30', '-t', '3', out1],
    capture_output=True, timeout=30)
print(f'Test 1 (color): rc={r.returncode}, exists={os.path.exists(out1)}')
if r.returncode != 0:
    print(f'stderr: {r.stderr.decode()[-500:]}')

# Test 2: with drawtext
out2 = os.path.join(tmpdir, 'test2.mp4')
r = subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'color=c=0x0a0a2a:s=1280x720:r=30:d=3',
    '-vf', "drawtext=text='Hello World':fontsize=28:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '30', '-t', '3', out2],
    capture_output=True, timeout=30)
print(f'Test 2 (drawtext): rc={r.returncode}, exists={os.path.exists(out2)}')
if r.returncode != 0:
    print(f'stderr: {r.stderr.decode()[-500:]}')

# Test 3: audio with say
say = shutil.which('say')
aiff = os.path.join(tmpdir, 'test.aiff')
r = subprocess.run([say, '-o', aiff, 'Hello world test'], capture_output=True, timeout=10)
print(f'Test 3 (say): rc={r.returncode}, exists={os.path.exists(aiff)}')

if os.path.exists(aiff):
    aac = os.path.join(tmpdir, 'test.aac')
    r = subprocess.run([ffmpeg, '-y', '-i', aiff, '-c:a', 'aac', '-b:a', '128k', '-t', '3', aac],
        capture_output=True, timeout=30)
    print(f'Test 3b (say to aac): rc={r.returncode}, exists={os.path.exists(aac)}')
    if r.returncode != 0:
        print(f'stderr: {r.stderr.decode()[-500:]}')

# Test 4: mux
if os.path.exists(out2) and os.path.exists(aac):
    muxed = os.path.join(tmpdir, 'muxed.mp4')
    r = subprocess.run([ffmpeg, '-y', '-i', out2, '-i', aac, '-c:v', 'copy', '-c:a', 'aac', '-shortest', muxed],
        capture_output=True, timeout=30)
    print(f'Test 4 (mux): rc={r.returncode}, exists={os.path.exists(muxed)}')
    if r.returncode != 0:
        print(f'stderr: {r.stderr.decode()[-500:]}')

# Test 5: concat
if os.path.exists(out2):
    concat_list = os.path.join(tmpdir, 'concat.txt')
    with open(concat_list, 'w') as f:
        f.write(f"file '{os.path.abspath(out2)}'\n")
        f.write(f"file '{os.path.abspath(out2)}'\n")
    concat_out = os.path.join(tmpdir, 'concat.mp4')
    r = subprocess.run([ffmpeg, '-y', '-f', 'concat', '-safe', '0', '-i', concat_list,
        '-c:v', 'libx264', '-c:a', 'aac', '-pix_fmt', 'yuv420p', concat_out],
        capture_output=True, timeout=30)
    print(f'Test 5 (concat): rc={r.returncode}, exists={os.path.exists(concat_out)}')
    if r.returncode != 0:
        print(f'stderr: {r.stderr.decode()[-500:]}')

shutil.rmtree(tmpdir)
