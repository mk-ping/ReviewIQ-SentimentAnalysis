from app.api.explorer import spike_z

assert spike_z([2, 3, 2], 10) is None, "too little history"
assert spike_z([2, 2, 2, 2], 9) is None, "flat history has no std"
z = spike_z([1, 3, 1, 3], 8)
assert z is not None and z > 2.5, z
assert spike_z([1, 3, 1, 3], 3) < 2.5
print("spike checks passed")
