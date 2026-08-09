char sub_18069C5E0()
{
  __int64 v0; // rax
  __int64 v1; // rax
  __int64 v2; // rcx
  __int64 v3; // rdx
  unsigned __int64 v4; // r8
  __int128 v5; // xmm0
  unsigned __int64 v6; // rdx
  unsigned __int64 v7; // rdx
  unsigned __int64 v8; // rdx
  unsigned __int64 v9; // rdx
  unsigned __int64 v10; // rdx
  unsigned __int64 v11; // rdx
  __int64 v12; // rcx
  __int64 v13; // rax
  __int64 v14; // rdi
  __int64 v15; // rbx
  unsigned __int64 v16; // r8
  __int64 i; // rdx
  __int64 v18; // rax
  __int64 v19; // rdi
  __int64 v20; // rbx
  unsigned __int64 v21; // r8
  unsigned __int64 j; // rdx
  __int64 v23; // rax
  __int64 v24; // rdi
  __int64 v25; // rbx
  unsigned __int64 v26; // r8
  unsigned __int64 k; // rdx
  __int64 v28; // rax
  __int64 v29; // rdi
  __int64 v30; // rbx
  unsigned __int64 v31; // r8
  unsigned __int64 m; // rdx
  __int64 v33; // rax
  __int64 v34; // rdi
  __int64 v35; // rbx
  unsigned __int64 v36; // r8
  unsigned __int64 n; // rdx
  __int64 v38; // rax
  __int64 v39; // rdi
  __int64 v40; // rbx
  unsigned __int64 v41; // r8
  __int64 ii; // rdx
  __int64 v43; // rax
  int *v44; // rbx
  __int64 v45; // rdi
  unsigned __int64 v46; // r8
  unsigned __int64 jj; // rdx
  __int64 v48; // r9
  int v49; // ecx
  int v50; // eax
  int v51; // r8d
  int v52; // ecx
  int v53; // edx
  int v54; // r10d
  int v55; // ecx
  int v56; // r10d
  char v58[32]; // [rsp+20h] [rbp-28h] BYREF

  strcpy(v58, "global-metadata.dat");
  v0 = sub_180693580(v58);
  qword_187E58E78 = v0;
  if ( v0 )
  {
    v1 = sub_18072F980(1044);
    v2 = qword_187E58E78;
    qword_187E58E98 = v1;
    v3 = v1;
    v4 = 8;
    do
    {
      v3 += 128;
      v5 = *(_OWORD *)v2;
      v2 += 128;
      *(_OWORD *)(v3 - 128) = v5;
      *(_OWORD *)(v3 - 112) = *(_OWORD *)(v2 - 112);
      *(_OWORD *)(v3 - 96) = *(_OWORD *)(v2 - 96);
      *(_OWORD *)(v3 - 80) = *(_OWORD *)(v2 - 80);
      *(_OWORD *)(v3 - 64) = *(_OWORD *)(v2 - 64);
      *(_OWORD *)(v3 - 48) = *(_OWORD *)(v2 - 48);
      *(_OWORD *)(v3 - 32) = *(_OWORD *)(v2 - 32);
      *(_OWORD *)(v3 - 16) = *(_OWORD *)(v2 - 16);
      --v4;
    }
    while ( v4 );
    *(_OWORD *)v3 = *(_OWORD *)v2;
    *(_DWORD *)(v3 + 16) = *(_DWORD *)(v2 + 16);
    v6 = 0xBC41EAFC33962B00uLL;
    do
    {
      v7 = v6 ^ (v6 << 13) ^ ((v6 ^ (v6 << 13)) >> 7) ^ ((v6 ^ (v6 << 13) ^ ((v6 ^ (v6 << 13)) >> 7)) << 17);
      *(_BYTE *)(v4 + v1) ^= byte_187356110[(unsigned __int8)(v7 ^ BYTE1(v7) ^ BYTE2(v7) ^ BYTE3(v7))];
      v8 = v7 ^ (v7 << 13) ^ ((v7 ^ (v7 << 13)) >> 7) ^ ((v7 ^ (v7 << 13) ^ ((v7 ^ (v7 << 13)) >> 7)) << 17);
      *(_BYTE *)(v4 + v1 + 1) ^= byte_187356110[(unsigned __int8)(v8 ^ BYTE1(v8) ^ BYTE2(v8) ^ BYTE3(v8))];
      v9 = v8 ^ (v8 << 13) ^ ((v8 ^ (v8 << 13)) >> 7) ^ ((v8 ^ (v8 << 13) ^ ((v8 ^ (v8 << 13)) >> 7)) << 17);
      *(_BYTE *)(v4 + v1 + 2) ^= byte_187356110[(unsigned __int8)(v9 ^ BYTE1(v9) ^ BYTE2(v9) ^ BYTE3(v9))];
      v10 = v9 ^ (v9 << 13) ^ ((v9 ^ (v9 << 13)) >> 7) ^ ((v9 ^ (v9 << 13) ^ ((v9 ^ (v9 << 13)) >> 7)) << 17);
      *(_BYTE *)(v4 + v1 + 3) ^= byte_187356110[(unsigned __int8)(v10 ^ BYTE1(v10) ^ BYTE2(v10) ^ BYTE3(v10))];
      v11 = v10 ^ (v10 << 13) ^ ((v10 ^ (v10 << 13)) >> 7) ^ ((v10 ^ (v10 << 13) ^ ((v10 ^ (v10 << 13)) >> 7)) << 17);
      *(_BYTE *)(v4 + v1 + 4) ^= byte_187356110[(unsigned __int8)(v11 ^ BYTE1(v11) ^ BYTE2(v11) ^ BYTE3(v11))];
      v6 = v11 ^ (v11 << 13) ^ ((v11 ^ (v11 << 13)) >> 7) ^ ((v11 ^ (v11 << 13) ^ ((v11 ^ (v11 << 13)) >> 7)) << 17);
      *(_BYTE *)(v4 + v1 + 5) ^= byte_187356110[(unsigned __int8)(v6 ^ BYTE1(v6) ^ BYTE2(v6) ^ BYTE3(v6))];
      v4 += 6LL;
    }
    while ( v4 < 0x414 );
    v12 = *(int *)(v1 + 1024);
    qword_187E58EA0 = v1;
    v13 = sub_18072F980(v12);
    v14 = qword_187E58EA0;
    v15 = v13;
    qword_187E58E70 = v13;
    sub_180757D70(v13, qword_187E58E78 + *(_DWORD *)(qword_187E58EA0 + 1020) - 1508, *(int *)(qword_187E58EA0 + 1024));
    v16 = 0;
    for ( i = 0x116C4B46EACABA5LL; v16 < *(int *)(v14 + 1024); ++v16 )
    {
      i ^= (i << 13)
         ^ ((i ^ (unsigned __int64)(i << 13)) >> 7)
         ^ ((i ^ (i << 13) ^ ((i ^ (unsigned __int64)(i << 13)) >> 7)) << 17);
      *(_BYTE *)(v16 + v15) ^= byte_187356110[(unsigned __int8)(i ^ BYTE1(i) ^ BYTE2(i) ^ BYTE3(i))];
    }
    v18 = sub_18072F980(*(int *)(v14 + 664));
    v19 = qword_187E58EA0;
    v20 = v18;
    qword_187E58E88 = v18;
    sub_180757D70(v18, qword_187E58E78 + *(_DWORD *)(qword_187E58EA0 + 660) + 3476, *(int *)(qword_187E58EA0 + 664));
    v21 = 0;
    for ( j = 0xD4C07427B74C818EuLL; v21 < *(int *)(v19 + 664); ++v21 )
    {
      j ^= (j << 13) ^ ((j ^ (j << 13)) >> 7) ^ ((j ^ (j << 13) ^ ((j ^ (j << 13)) >> 7)) << 17);
      *(_BYTE *)(v21 + v20) ^= byte_187356110[(unsigned __int8)(j ^ BYTE1(j) ^ BYTE2(j) ^ BYTE3(j))];
    }
    v23 = sub_18072F980(*(int *)(v19 + 964));
    v24 = qword_187E58EA0;
    v25 = v23;
    qword_187E58EB0 = v23;
    sub_180757D70(v23, qword_187E58E78 + *(_DWORD *)(qword_187E58EA0 + 960) - 6696, *(int *)(qword_187E58EA0 + 964));
    v26 = 0;
    for ( k = 0xAFDAE7074F40F834uLL; v26 < *(int *)(v24 + 964); ++v26 )
    {
      k ^= (k << 13) ^ ((k ^ (k << 13)) >> 7) ^ ((k ^ (k << 13) ^ ((k ^ (k << 13)) >> 7)) << 17);
      *(_BYTE *)(v26 + v25) ^= byte_187356110[(unsigned __int8)(k ^ BYTE1(k) ^ BYTE2(k) ^ BYTE3(k))];
    }
    v28 = sub_18072F980(*(int *)(v24 + 136));
    v29 = qword_187E58EA0;
    v30 = v28;
    qword_187E58E68 = v28;
    sub_180757D70(v28, qword_187E58E78 + *(_DWORD *)(qword_187E58EA0 + 132) + 4304, *(int *)(qword_187E58EA0 + 136));
    v31 = 0;
    for ( m = 0xA28BFC303CE665BAuLL; v31 < *(int *)(v29 + 136); ++v31 )
    {
      m ^= (m << 13) ^ ((m ^ (m << 13)) >> 7) ^ ((m ^ (m << 13) ^ ((m ^ (m << 13)) >> 7)) << 17);
      *(_BYTE *)(v31 + v30) ^= byte_187356110[(unsigned __int8)(m ^ BYTE1(m) ^ BYTE2(m) ^ BYTE3(m))];
    }
    v33 = sub_18072F980(*(int *)(v29 + 592));
    v34 = qword_187E58EA0;
    v35 = v33;
    qword_187E58E40 = v33;
    sub_180757D70(v33, qword_187E58E78 + *(_DWORD *)(qword_187E58EA0 + 588) - 3984, *(int *)(qword_187E58EA0 + 592));
    v36 = 0;
    for ( n = 0xFF3532DDAC34BA66uLL; v36 < *(int *)(v34 + 592); ++v36 )
    {
      n ^= (n << 13) ^ ((n ^ (n << 13)) >> 7) ^ ((n ^ (n << 13) ^ ((n ^ (n << 13)) >> 7)) << 17);
      *(_BYTE *)(v36 + v35) ^= byte_187356110[(unsigned __int8)(n ^ BYTE1(n) ^ BYTE2(n) ^ BYTE3(n))];
    }
    v38 = sub_18072F980(*(int *)(v34 + 652));
    v39 = qword_187E58EA0;
    v40 = v38;
    qword_187E58E60 = v38;
    sub_180757D70(v38, qword_187E58E78 + *(_DWORD *)(qword_187E58EA0 + 648) - 7080, *(int *)(qword_187E58EA0 + 652));
    v41 = 0;
    for ( ii = 0x1DFCEDD20A3EE02CLL; v41 < *(int *)(v39 + 652); ++v41 )
    {
      ii ^= (ii << 13)
          ^ ((ii ^ (unsigned __int64)(ii << 13)) >> 7)
          ^ ((ii ^ (ii << 13) ^ ((ii ^ (unsigned __int64)(ii << 13)) >> 7)) << 17);
      *(_BYTE *)(v41 + v40) ^= byte_187356110[(unsigned __int8)(ii ^ BYTE1(ii) ^ BYTE2(ii) ^ BYTE3(ii))];
    }
    v43 = sub_18072F980(*(int *)(v39 + 4));
    v44 = (int *)qword_187E58EA0;
    v45 = v43;
    qword_187E58E90 = v43;
    sub_180757D70(v43, qword_187E58E78 + *(_DWORD *)qword_187E58EA0 + 2268, *(int *)(qword_187E58EA0 + 4));
    v46 = 0;
    for ( jj = 0x88942C9716431E06uLL; v46 < v44[1]; ++v46 )
    {
      jj ^= (jj << 13) ^ ((jj ^ (jj << 13)) >> 7) ^ ((jj ^ (jj << 13) ^ ((jj ^ (jj << 13)) >> 7)) << 17);
      *(_BYTE *)(v46 + v45) ^= byte_187356110[(unsigned __int8)(jj ^ BYTE1(jj) ^ BYTE2(jj) ^ BYTE3(jj))];
    }
    v48 = v44[74];
    dword_187E59220 = v48;
    dword_187E59230 = v44[35];
    dword_187E59158 = v48;
    v49 = *(_DWORD *)(qword_187E58EA8 + 48);
    v50 = 1;
    if ( v49 > 255 )
    {
      v51 = 4;
      if ( v49 <= 0xFFFF )
        v51 = 2;
    }
    else
    {
      v51 = 1;
    }
    v52 = v44[239];
    if ( v52 > 255 )
    {
      v53 = 4;
      if ( v52 <= 0xFFFF )
        v53 = 2;
    }
    else
    {
      v53 = 1;
    }
    v54 = v44[98];
    if ( v54 > 255 )
    {
      v55 = 4;
      if ( v54 <= 0xFFFF )
        v55 = 2;
    }
    else
    {
      v55 = 1;
    }
    v56 = v44[206];
    if ( v56 > 255 )
    {
      v50 = 4;
      if ( v56 <= 0xFFFF )
        v50 = 2;
    }
    LODWORD(qword_187E58E54) = v53;
    HIDWORD(qword_187E58E54) = v55;
    dword_187E58E5C = v50;
    dword_187E58E50 = v51;
    qword_187E59188 = off_187E55B28(v48, 24);
    qword_187E59168 = off_187E55B28(*(int *)(qword_187E58EA8 + 48), 8);
    qword_187E59170 = off_187E55B28(*(int *)(qword_187E58EA0 + 956), 8);
    qword_187E59160 = off_187E55B28(*(int *)(qword_187E58EA0 + 968), 8);
    sub_18069C540();
    LOBYTE(v0) = 1;
  }
  return v0;
}