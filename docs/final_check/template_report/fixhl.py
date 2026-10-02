import zipfile,re,shutil,sys
src=sys.argv[1]; tmp=src+'.tmp'
with zipfile.ZipFile(src) as zi, zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as zo:
    for it in zi.infolist():
        data=zi.read(it.filename)
        if it.filename=='word/document.xml':
            data=re.sub(rb'<w:highlightCs [^>]*/>',b'',data)
        zo.writestr(it,data)
shutil.move(tmp,src); print('fixed')
