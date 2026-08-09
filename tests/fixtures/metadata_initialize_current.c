char sub_1806AB0E0()
{
  const void *v0; // rax
  __int64 v1; // rbx
  _OWORD *v2; // rax
  __int64 v3; // rdx
  __int64 v4; // r9
  _OWORD *v5; // rcx
  __int64 v6; // r8
  __int128 v7; // xmm0
  int v8; // eax
  __int64 v9; // rdx
  unsigned __int64 v10; // rcx
  unsigned __int64 v11; // rcx
  size_t v12; // rcx
  void *v13; // rax
  __int64 v14; // rdi
  __int64 v15; // rbx
  unsigned __int64 v16; // rdx
  __int64 v17; // r8
  unsigned __int64 v18; // rdx
  void *v19; // rax
  __int64 v20; // rdi
  __int64 v21; // rbx
  unsigned __int64 v22; // rdx
  __int64 v23; // r8
  unsigned __int64 v24; // rdx
  void *v25; // rax
  __int64 v26; // rdi
  __int64 v27; // rbx
  unsigned __int64 v28; // rdx
  __int64 v29; // r8
  unsigned __int64 v30; // rdx
  void *v31; // rax
  __int64 v32; // rdi
  __int64 v33; // rbx
  unsigned __int64 v34; // rdx
  __int64 v35; // r8
  unsigned __int64 v36; // rdx
  void *v37; // rax
  __int64 v38; // rdi
  __int64 v39; // rbx
  unsigned __int64 v40; // rdx
  __int64 v41; // r8
  unsigned __int64 v42; // rdx
  void *v43; // rax
  __int64 v44; // rdi
  __int64 v45; // rbx
  unsigned __int64 v46; // rdx
  __int64 v47; // r8
  unsigned __int64 v48; // rdx
  void *v49; // rax
  _DWORD *v50; // rdi
  __int64 v51; // rbx
  unsigned __int64 v52; // rdx
  __int64 v53; // r8
  unsigned __int64 v54; // rdx
  __int64 v55; // r10
  int v56; // edx
  int v57; // eax
  int v58; // ecx
  int v59; // edx
  int v60; // r8d
  int v61; // r9d
  int v62; // edx
  int v63; // r9d
  char v65[32]; // [rsp+20h] [rbp-28h] BYREF

  strcpy(v65, "global-metadata.dat");
  v0 = sub_1806A2460(v65);
  qword_1882E73E0 = (__int64)v0;
  if ( v0 )
  {
    v1 = 756;
    v2 = j__malloc_base(0x2F4u);
    v3 = qword_1882E73E0;
    v4 = (__int64)v2;
    qword_1882E7400 = (__int64)v2;
    v5 = v2;
    v6 = 5;
    do
    {
      v5 += 8;
      v7 = *(_OWORD *)v3;
      v3 += 128;
      *(v5 - 8) = v7;
      *(v5 - 7) = *(_OWORD *)(v3 - 112);
      *(v5 - 6) = *(_OWORD *)(v3 - 96);
      *(v5 - 5) = *(_OWORD *)(v3 - 80);
      *(v5 - 4) = *(_OWORD *)(v3 - 64);
      *(v5 - 3) = *(_OWORD *)(v3 - 48);
      *(v5 - 2) = *(_OWORD *)(v3 - 32);
      *(v5 - 1) = *(_OWORD *)(v3 - 16);
      --v6;
    }
    while ( v6 );
    *v5 = *(_OWORD *)v3;
    v5[1] = *(_OWORD *)(v3 + 16);
    v5[2] = *(_OWORD *)(v3 + 32);
    v5[3] = *(_OWORD *)(v3 + 48);
    v5[4] = *(_OWORD *)(v3 + 64);
    v5[5] = *(_OWORD *)(v3 + 80);
    v5[6] = *(_OWORD *)(v3 + 96);
    v8 = *(_DWORD *)(v3 + 112);
    v9 = v4;
    *((_DWORD *)v5 + 28) = v8;
    v10 = 0xE039BA990B051CD7uLL;
    do
    {
      ++v9;
      v11 = (((v10 << 13) ^ v10) >> 7) ^ (v10 << 13) ^ v10;
      v10 = (v11 << 17) ^ v11;
      *(_BYTE *)(v9 - 1) ^= byte_18759C190[(unsigned __int8)(v10
                                                           ^ ((unsigned __int16)(v10
                                                                               ^ (((unsigned int)v10
                                                                                 ^ (unsigned int)(v10 >> 8)) >> 8)) >> 8))];
      --v1;
    }
    while ( v1 );
    v12 = *(int *)(v4 + 216);
    qword_1882E7408 = v4;
    v13 = j__malloc_base(v12);
    v14 = qword_1882E7408;
    v15 = (__int64)v13;
    qword_1882E73C8 = (__int64)v13;
    memmove(
      v13,
      (const void *)(qword_1882E73E0 + *(_DWORD *)(qword_1882E7408 + 224) - 6756),
      *(int *)(qword_1882E7408 + 216));
    v16 = 0x6437F7B47BCC353DLL;
    if ( *(_DWORD *)(v14 + 216) )
    {
      v17 = -v15;
      do
      {
        ++v15;
        v18 = (((v16 << 13) ^ v16) >> 7) ^ (v16 << 13) ^ v16;
        v16 = (v18 << 17) ^ v18;
        *(_BYTE *)(v15 - 1) ^= byte_18759C190[(unsigned __int8)(v16
                                                              ^ ((unsigned __int16)(v16
                                                                                  ^ (((unsigned int)v16
                                                                                    ^ (unsigned int)(v16 >> 8)) >> 8)) >> 8))];
      }
      while ( v17 + v15 < (unsigned __int64)*(int *)(v14 + 216) );
    }
    v19 = j__malloc_base(*(int *)(v14 + 420));
    v20 = qword_1882E7408;
    v21 = (__int64)v19;
    qword_1882E73F0 = (__int64)v19;
    memmove(
      v19,
      (const void *)(qword_1882E73E0 + *(_DWORD *)(qword_1882E7408 + 428) + 5028),
      *(int *)(qword_1882E7408 + 420));
    v22 = 0x2991189FDDC51967LL;
    if ( *(_DWORD *)(v20 + 420) )
    {
      v23 = -v21;
      do
      {
        ++v21;
        v24 = (((v22 << 13) ^ v22) >> 7) ^ (v22 << 13) ^ v22;
        v22 = (v24 << 17) ^ v24;
        *(_BYTE *)(v21 - 1) ^= byte_18759C190[(unsigned __int8)(v22
                                                              ^ ((unsigned __int16)(v22
                                                                                  ^ (((unsigned int)v22
                                                                                    ^ (unsigned int)(v22 >> 8)) >> 8)) >> 8))];
      }
      while ( v23 + v21 < (unsigned __int64)*(int *)(v20 + 420) );
    }
    v25 = j__malloc_base(*(int *)(v20 + 144));
    v26 = qword_1882E7408;
    v27 = (__int64)v25;
    qword_1882E7418 = (__int64)v25;
    memmove(
      v25,
      (const void *)(qword_1882E73E0 + *(_DWORD *)(qword_1882E7408 + 152) + 8036),
      *(int *)(qword_1882E7408 + 144));
    v28 = 0x5647FAF029DA7235LL;
    if ( *(_DWORD *)(v26 + 144) )
    {
      v29 = -v27;
      do
      {
        ++v27;
        v30 = (((v28 << 13) ^ v28) >> 7) ^ (v28 << 13) ^ v28;
        v28 = (v30 << 17) ^ v30;
        *(_BYTE *)(v27 - 1) ^= byte_18759C190[(unsigned __int8)(v28
                                                              ^ ((unsigned __int16)(v28
                                                                                  ^ (((unsigned int)v28
                                                                                    ^ (unsigned int)(v28 >> 8)) >> 8)) >> 8))];
      }
      while ( v29 + v27 < (unsigned __int64)*(int *)(v26 + 144) );
    }
    v31 = j__malloc_base(*(int *)(v26 + 408));
    v32 = qword_1882E7408;
    v33 = (__int64)v31;
    qword_1882E73A8 = (__int64)v31;
    memmove(
      v31,
      (const void *)(qword_1882E73E0 + *(_DWORD *)(qword_1882E7408 + 416) - 404),
      *(int *)(qword_1882E7408 + 408));
    v34 = 0x9B1470F67FDC86B4uLL;
    if ( *(_DWORD *)(v32 + 408) )
    {
      v35 = -v33;
      do
      {
        ++v33;
        v36 = (((v34 << 13) ^ v34) >> 7) ^ (v34 << 13) ^ v34;
        v34 = (v36 << 17) ^ v36;
        *(_BYTE *)(v33 - 1) ^= byte_18759C190[(unsigned __int8)(v34
                                                              ^ ((unsigned __int16)(v34
                                                                                  ^ (((unsigned int)v34
                                                                                    ^ (unsigned int)(v34 >> 8)) >> 8)) >> 8))];
      }
      while ( v35 + v33 < (unsigned __int64)*(int *)(v32 + 408) );
    }
    v37 = j__malloc_base(*(int *)(v32 + 396));
    v38 = qword_1882E7408;
    v39 = (__int64)v37;
    qword_1882E73F8 = (__int64)v37;
    memmove(
      v37,
      (const void *)(qword_1882E73E0 + *(_DWORD *)(qword_1882E7408 + 404) - 4112),
      *(int *)(qword_1882E7408 + 396));
    v40 = 0x1CEDA6B470922C8LL;
    if ( *(_DWORD *)(v38 + 396) )
    {
      v41 = -v39;
      do
      {
        ++v39;
        v42 = (((v40 << 13) ^ v40) >> 7) ^ (v40 << 13) ^ v40;
        v40 = (v42 << 17) ^ v42;
        *(_BYTE *)(v39 - 1) ^= byte_18759C190[(unsigned __int8)(v40
                                                              ^ ((unsigned __int16)(v40
                                                                                  ^ (((unsigned int)v40
                                                                                    ^ (unsigned int)(v40 >> 8)) >> 8)) >> 8))];
      }
      while ( v41 + v39 < (unsigned __int64)*(int *)(v38 + 396) );
    }
    v43 = j__malloc_base(*(int *)(v38 + 36));
    v44 = qword_1882E7408;
    v45 = (__int64)v43;
    qword_1882E73D8 = (__int64)v43;
    memmove(
      v43,
      (const void *)(qword_1882E73E0 + *(_DWORD *)(qword_1882E7408 + 44) + 4228),
      *(int *)(qword_1882E7408 + 36));
    v46 = 0x3B596B9B21B69FF1LL;
    if ( *(_DWORD *)(v44 + 36) )
    {
      v47 = -v45;
      do
      {
        ++v45;
        v48 = (((v46 << 13) ^ v46) >> 7) ^ (v46 << 13) ^ v46;
        v46 = (v48 << 17) ^ v48;
        *(_BYTE *)(v45 - 1) ^= byte_18759C190[(unsigned __int8)(v46
                                                              ^ ((unsigned __int16)(v46
                                                                                  ^ (((unsigned int)v46
                                                                                    ^ (unsigned int)(v46 >> 8)) >> 8)) >> 8))];
      }
      while ( v47 + v45 < (unsigned __int64)*(int *)(v44 + 36) );
    }
    v49 = j__malloc_base(*(int *)(v44 + 684));
    v50 = (_DWORD *)qword_1882E7408;
    v51 = (__int64)v49;
    qword_1882E73D0 = (__int64)v49;
    memmove(
      v49,
      (const void *)(qword_1882E73E0 + *(_DWORD *)(qword_1882E7408 + 692) + 7856),
      *(int *)(qword_1882E7408 + 684));
    v52 = 0x6E47EB74067D4A7FLL;
    if ( v50[171] )
    {
      v53 = -v51;
      do
      {
        ++v51;
        v54 = (((v52 << 13) ^ v52) >> 7) ^ (v52 << 13) ^ v52;
        v52 = (v54 << 17) ^ v54;
        *(_BYTE *)(v51 - 1) ^= byte_18759C190[(unsigned __int8)(v52
                                                              ^ ((unsigned __int16)(v52
                                                                                  ^ (((unsigned int)v52
                                                                                    ^ (unsigned int)(v52 >> 8)) >> 8)) >> 8))];
      }
      while ( v53 + v51 < (unsigned __int64)(int)v50[171] );
    }
    v55 = (int)v50[58];
    dword_1882E7780 = v55;
    dword_1882E7784 = v50[172];
    dword_1882E76B0 = v55;
    v56 = *(_DWORD *)(qword_1882E7410 + 48);
    v57 = 1;
    if ( v56 > 255 )
    {
      v58 = 4;
      if ( v56 <= 0xFFFF )
        v58 = 2;
    }
    else
    {
      v58 = 1;
    }
    v59 = v50[40];
    if ( v59 > 255 )
    {
      v60 = 4;
      if ( v59 <= 0xFFFF )
        v60 = 2;
    }
    else
    {
      v60 = 1;
    }
    v61 = v50[154];
    if ( v61 > 255 )
    {
      v62 = 4;
      if ( v61 <= 0xFFFF )
        v62 = 2;
    }
    else
    {
      v62 = 1;
    }
    v63 = v50[184];
    if ( v63 > 255 )
    {
      v57 = 4;
      if ( v63 <= 0xFFFF )
        v57 = 2;
    }
    dword_1882E73B8 = v58;
    HIDWORD(qword_1882E73BC) = v62;
    LODWORD(qword_1882E73BC) = v60;
    dword_1882E73C4 = v57;
    qword_1882E76E8 = off_1882E39B0(v55, 24);
    qword_1882E76C8 = off_1882E39B0(*(int *)(qword_1882E7410 + 48), 8);
    qword_1882E76E0 = off_1882E39B0(*(int *)(qword_1882E7408 + 160), 8);
    qword_1882E76B8 = off_1882E39B0(*(int *)(qword_1882E7408 + 148), 8);
    sub_1806AB020();
    LOBYTE(v0) = 1;
  }
  return (char)v0;
}
