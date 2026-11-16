with open('src/main.ykn', 'r') as f:
    content = f.read()

old = '''    fun mt_read(ci: int64) {
        eprint("[ypwee] mt: read ci=" + i64_to_string(ci) + "\n")
        set idopt = this.c_id.get_i64(ci)
        if idopt == null { return }
        set chunk: string = ""
        sus {
            set cs = init TcpStream(cast(idopt ?? 0, "uint64"))
            rewrite chunk = cs.read(16384)
        } catch {
            this.drop_client(ci)
            return
        }
        if chunk.len() == 0 {
            this.drop_client(ci)
            return
        }
        this.c_idletick.set_i64(ci, this.tick)
        eprint("[ypwee] mt: chunk.len=" + i64_to_string(cast(chunk.len(), "int64")) + "\n")
        set prev: string = this.mt_state_get(ci)
        set acc: string = prev + chunk
        if acc.len() > MT_MAX_ACC {
            this.drop_client(ci)
            return
        }
        this.mt_state_set(ci, acc)
        this.mt_step(ci)
        // oneshot poller: перезаряжаем клиентский сокет после каждого чтения
        this.rearm(ci)
    }'''

new = '''    fun mt_read(ci: int64) {
        eprint("[ypwee] mt: read ci=" + i64_to_string(ci) + "\n")
        set idopt = this.c_id.get_i64(ci)
        if idopt == null { return }
        set buf: uint8[] = []
        buf.reserve(16384)
        set k: int64 = 0
        while k < 16384 {
            buf.push(0u8)
            rewrite k += 1
        }
        set got: int64 = 0
        sus {
            set cs = init TcpStream(cast(idopt ?? 0, "uint64"))
            rewrite got = cs.read_bytes(cast(buf.as_ptr(), "ptr<uint8>"), 16384)
        } catch {
            this.drop_client(ci)
            return
        }
        if got <= 0 {
            this.drop_client(ci)
            return
        }
        this.c_idletick.set_i64(ci, this.tick)
        // build string from buf[0..got]
        set chunk: bytes = cast("", "bytes")
        chunk.reserve(got)
        set i: int64 = 0
        while i < got {
            chunk.push(buf[i])
            rewrite i += 1
        }
        set chunk_s: string = cast(chunk, "string")
        set prev: string = this.mt_state_get(ci)
        set acc: string = prev + chunk_s
        if acc.len() > MT_MAX_ACC {
            this.drop_client(ci)
            return
        }
        this.mt_state_set(ci, acc)
        this.mt_step(ci)
        // oneshot poller: перезаряжаем клиентский сокет после каждого чтения
        this.rearm(ci)
    }'''

if old in content:
    content = content.replace(old, new)
    with open('src/main.ykn', 'w') as f:
        f.write(content)
    print("Fixed mt_read")
else:
    print("Old mt_read block not found")
    idx = content.find('fun mt_read')
    if idx >= 0:
        print(content[idx:idx+800])
