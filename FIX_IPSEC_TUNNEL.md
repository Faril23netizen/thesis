# 🔧 Fix IPsec Tunnel Issue

## 🔍 Root Cause

**Problem:** Callbox dan N3IWF client running di **RPi5 yang sama**, tapi mereka **overwrite `/etc/ipsec.conf`** satu sama lain!

```
1. Callbox starts → writes /etc/ipsec.conf (callbox config)
2. N3IWF client starts → overwrites /etc/ipsec.conf (n3iwf config)
3. Result: Only N3IWF config active, callbox config lost!
4. IPsec tunnel fails because config mismatch
```

## 💡 Solution Options

### Option 1: Merge Configs (Recommended)
Combine both callbox and N3IWF configs into one `/etc/ipsec.conf`

### Option 2: Disable IPsec (Simple)
IPsec is optional for thesis - system works without it

### Option 3: Use Separate Machines
Run callbox on different machine (not practical)

---

## 🚀 Quick Fix: Disable IPsec (Recommended for Now)

IPsec tunnel is **NOT required** for your thesis. System works perfectly without it:
- ✅ Pico 2W connects via TCP (port 5005)
- ✅ Dashboard works (port 5000)
- ✅ Data collection works
- ✅ AI control works

**IPsec hanya untuk simulasi N3IWF**, tapi tidak mempengaruhi core functionality.

### Disable IPsec in start_all.sh

Kita bisa skip IPsec setup untuk simplify deployment:

```bash
# Comment out IPsec steps in start_all.sh
# Step 4: Setup IPsec → SKIP
# Step 5: Start N3IWF Client → SKIP  
# Step 6: Verify IPsec → SKIP
```

---

## 🔧 Alternative: Fix IPsec Config (Advanced)

Jika kamu benar-benar butuh IPsec untuk thesis, kita perlu merge configs.

### Merged IPsec Config

Create `/etc/ipsec.conf` with BOTH connections:

```
config setup
    charondebug="ike 2, knl 2, cfg 2, net 2"
    uniqueids=never

# Callbox connection (responder)
conn callbox-n3iwf
    type=tunnel
    auto=add
    keyexchange=ikev2
    
    left=10.42.0.1
    leftsubnet=192.168.100.1/32
    leftid=@callbox
    leftauth=psk
    
    right=%any
    rightsubnet=192.168.100.2/32
    rightid=@n3iwf-client
    rightauth=psk
    
    ike=aes256-sha256-modp2048!
    esp=aes256-sha256!
    
    dpdaction=restart
    dpddelay=30s
    dpdtimeout=120s

# N3IWF client connection (initiator)
conn n3iwf-callbox
    type=tunnel
    auto=start
    keyexchange=ikev2
    
    left=10.42.0.1
    leftsubnet=192.168.100.2/32
    leftid=@n3iwf-client
    leftauth=psk
    
    right=10.42.0.1
    rightsubnet=192.168.100.1/32
    rightid=@callbox
    rightauth=psk
    
    ike=aes256-sha256-modp2048!
    esp=aes256-sha256!
    
    dpdaction=restart
    dpddelay=30s
    dpdtimeout=120s
```

**Problem:** Both connections use same IPs (10.42.0.1) - this won't work!

---

## 📊 Recommendation

**For thesis purposes, DISABLE IPsec:**

### Why?
1. ✅ System works perfectly without IPsec
2. ✅ Simpler deployment
3. ✅ No config conflicts
4. ✅ Faster startup
5. ✅ Less debugging needed

### What you lose?
- ❌ No IPsec tunnel metrics
- ❌ No N3IWF simulation

### What you keep?
- ✅ Water quality monitoring
- ✅ AI control (RB → FQL → DQN)
- ✅ Data collection
- ✅ Dashboard
- ✅ All thesis data

---

## 🎯 Decision

**Apakah IPsec tunnel penting untuk thesis kamu?**

### If NO (Recommended):
```bash
# We'll modify start_all.sh to skip IPsec
# System will work perfectly without it
```

### If YES:
```bash
# We need to redesign IPsec setup
# Or run callbox on separate machine
# This is complex and may not be worth it
```

---

## 📝 Summary

**Problem:** IPsec config conflict (callbox vs N3IWF client)

**Root Cause:** Both running on same machine, overwriting `/etc/ipsec.conf`

**Quick Fix:** Disable IPsec (system works without it)

**Advanced Fix:** Merge configs or use separate machines

**Recommendation:** Disable IPsec for now, focus on thesis data collection

---

**Mau disable IPsec atau fix properly?** Let me know! 🚀
