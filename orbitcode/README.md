# OrbitCode

বৃত্তাকার কক্ষপথে সাজানো নোড ও সংযোগ-রেখার 2D কোড। দেখতে QR-এর মতো নয়। এই প্যাকেজে আছে encoder, decoder,
কমান্ড লাইন (`orbitcode`) ও ওয়েব পেজ (`orbitcode-web`)।

| পণ্য | কী |
|---|---|
| **MonoOrbit™** | কালো + ৩ ধূসর স্তর, সাদা কাগজে শুধু কালো কালিতে ছাপা যায়। ক্ষমতা ~২০৪ বাইট |
| **ColourOrbit™** | ৮ রঙ, গাঢ় পটভূমি, স্ক্রিনের জন্য। ক্ষমতা ~২৭৪ বাইট |
| **SecureOrbit™** | ঐচ্ছিক নিরাপত্তা-স্তর (পাসওয়ার্ড এনক্রিপশন ও/অথবা স্বাক্ষর), দুই সংস্করণেই। বন্ধ থাকলে কোড খোলা |

## ইনস্টল

    pip install orbitcode            # লাইব্রেরি + CLI
    pip install "orbitcode[web]"     # সঙ্গে ওয়েব পেজ (Flask)

স্থানীয় ফাইল থেকে: `pip install ./orbitcode-0.1.0-py3-none-any.whl` অথবা সোর্স ফোল্ডারে `pip install -e ".[dev]"`।
Python 3.9+ লাগবে।

## কমান্ড লাইন

    orbitcode encode "হ্যালো" -o a.png                       # MonoOrbit (ডিফল্ট)
    orbitcode encode "হ্যালো" --version colour -o b.png       # ColourOrbit
    orbitcode encode -f file.txt -o c.png --scale 3          # ফাইল থেকে, বড় ছবি
    orbitcode decode a.png                                   # পড়া (সংস্করণ নিজে চেনা হয়)
    orbitcode decode f1.png f2.png f3.png                    # একাধিক ফ্রেম একসঙ্গে
    orbitcode decode a.png -o out.bin                        # ফাইলে লেখা

**SecureOrbit (ঐচ্ছিক)**

    orbitcode encode "গোপন" --password orbit123 -o s.png
    orbitcode decode s.png --password orbit123
    orbitcode keygen                                         # স্বাক্ষরের key জোড়া
    orbitcode encode "বার্তা" --sign-key <private> -o t.png
    orbitcode decode t.png --verify-key <public>

`python -m orbitcode ...` একই কাজ করে।

## ওয়েব পেজ

    orbitcode-web                    # বা: orbitcode serve
    orbitcode-web --port 8080

এরপর `http://127.0.0.1:5000` খুলুন। সংস্করণ বাছুন, লিখুন, চাইলে SecureOrbit অংশ খুলে পাসওয়ার্ড বা স্বাক্ষর দিন।
ডিফল্টে শুধু আপনার নিজের কম্পিউটারে চলে। অন্য নেটওয়ার্কে খুললে (`--host 0.0.0.0`) পাসওয়ার্ড ও private key সার্ভারে যায়, তাই বিশ্বস্ত নেটওয়ার্ক ও HTTPS ছাড়া করবেন না।

## Python থেকে

    import cv2, orbitcode as oc

    img = oc.encode("hello".encode(), version="mono", password="orbit123")   # PIL ছবি
    img.save("a.png")
    data, info = oc.decode_images([cv2.imread("a.png")], password="orbit123")
    # info = {'version': 'mono', 'frames': 1, 'encrypted': True, 'signature': 'none'}

    priv, pub = oc.new_keypair()
    oc.capacity("mono", password=True, sign=True)                           # ~৯৬ বাইট

ভুল পাসওয়ার্ড, জাল স্বাক্ষর বা বদলানো কোডে `orbitcode.SecurityError` (একটি `ValueError`) ওঠে।

## কীভাবে কাজ করে (সংক্ষেপে)

- **গঠন:** ১৬টি বৃত্তাকার স্তরে প্রায় ১১০০ নোড। MonoOrbit-এ নোডপ্রতি ২ bit (৪ ধূসর স্তর), ColourOrbit-এ ৩ bit (৮ রঙ), আর পাশের নোডের রেখা আছে/নেই ১ bit। চার anchor, মাঝে calibration নোড।
- **Encode:** zlib -> হেডার ও CRC32 -> whitening -> LDPC (rate 1/2) -> interleave -> আঁকা।
- **Decode:** anchor থেকে perspective সোজা -> আলোর সংশোধন ও soft LLR (Mono: flat-field, Colour: Lab) -> Dijkstra দিয়ে edge পড়া -> একাধিক ফ্রেমের LLR যোগ -> LDPC min-sum -> CRC।
- **SecureOrbit:** scrypt + ChaCha20-Poly1305 এনক্রিপশন, Ed25519 স্বাক্ষর (`cryptography` লাইব্রেরি, নিজের বানানো সাইফার নয়)। খরচ: এনক্রিপশন ৪৪ বাইট, স্বাক্ষর ৬৪ বাইট, ফ্ল্যাগ ১ বাইট।

| ক্ষমতা (বাইট) | খোলা | এনক্রিপ্টেড | স্বাক্ষরিত | দুটোই |
|---|---|---|---|---|
| MonoOrbit | ২০৪ | ১৬০ | ১৪০ | ৯৬ |
| ColourOrbit | ২৭৪ | ২৩০ | ২১০ | ১৬৬ |

## ডেভেলপমেন্ট

    pip install -e ".[dev]"
    pytest                      # round-trip, SecureOrbit, CLI ও ওয়েব API-র টেস্ট
    pip install build && python -m build      # dist/ এ wheel ও sdist

## সীমাবদ্ধতা

- **আসল ফোন-ক্যামেরা, ছায়া ও ছাপা কাগজে এখনো পরীক্ষা হয়নি।** টেস্টগুলো পরিষ্কার ছবিতে। MonoOrbit-এ তীব্র ছায়ায় পাশের ধূসর স্তর গুলিয়ে যেতে পারে।
- **নিরাপত্তা-নিরীক্ষা হয়নি।** লাইব্রেরি প্রমাণিত, কিন্তু আমাদের ব্যবহার কোনো বিশেষজ্ঞ যাচাই করেননি।
- **ছবি তুলে আবার দেখালে কোড আবার পড়া যায়**; এককালীন কোডের জন্য সার্ভারে গণনা লাগবে, যা এখানে নেই।
- মোবাইলের ক্যামেরা এটি নিজে পড়ে না, এই decoder লাগে।
- `orbitcode` নামটি PyPI-তে আগে থেকে নেওয়া থাকতে পারে। প্রকাশের আগে নাম ও ট্রেডমার্ক (™) যাচাই করুন, আর একটি লাইসেন্স বেছে `LICENSE` ফাইল যোগ করুন।
