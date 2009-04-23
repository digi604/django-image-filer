import os
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseForbidden,HttpResponseBadRequest
from django.contrib.sessions.models import Session
from django.conf import settings

from models import Folder, FolderRoot, Image, Bucket, BucketItem

from django import forms

class NewFolderForm(forms.ModelForm):
    class Meta:
        model = Folder
        fields = ('name', )

def _userperms(item, request):
    r = []
    ps = ['read', 'edit', 'add_children']
    for p in ps:
        attr = "has_%s_permission" % p
        if hasattr(item, attr):
            x = getattr(item, attr)(request)
            if x:
                r.append( p )
    return r

def directory_listing(request, folder_id=None):
    #print request.session.session_key, request.user, type(request.session)
    #print "%s.SessionStore" % settings.SESSION_ENGINE
    new_folder_form = NewFolderForm()
    #print request.user
    
    if not folder_id == None:
        folder = Folder.objects.get(id=folder_id)
        #print "readX: %s" % getattr(folder, 'has_read_permission')(request)
        #print "readX2: %s" % folder.has_read_permission(request)
    else:
        folder = FolderRoot()
    
    
    # Debug    
    upload_file_form = UploadFileForm()
    
    folder_children = []
    folder_files = []
    if type(folder) == FolderRoot:
        for f in folder.children:
            f.perms = _userperms(f, request)
            folder_children.append(f)
    else:
        for f in folder.children.all():
            f.perms = _userperms(f, request)
            if hasattr(f, 'has_read_permission'):
                if f.has_read_permission(request):
                    folder_children.append(f)
            else:
                folder_children.append(f) 
        for f in folder.files:
            f.perms = _userperms(f, request)
            if hasattr(f, 'has_read_permission'):
                if f.has_read_permission(request):
                    folder_files.append(f)
            else:
                folder_files.append(f)
    try:
        permissions = {
            'has_edit_permission': folder.has_edit_permission(request),
            'has_read_permission': folder.has_read_permission(request),
            'has_add_children_permission': folder.has_add_children_permission(request),
        }
    except:
        permissions = {}
    
    #print folder_files
    #print folder_children
    return render_to_response('image_filer/directory_listing.html', {
            'folder':folder,
            'folder_children':folder_children,
            'folder_files':folder_files,
            'new_folder_form': new_folder_form,
            'upload_file_form': upload_file_form,
            'permissions': permissions,
            'permstest': _userperms(folder, request)
        }, context_instance=RequestContext(request))

def edit_folder(request, folder_id):
    # TODO: implement edit_folder view
    folder=None
    return render_to_response('image_filer/folder_edit.html', {
            'folder':folder,
        }, context_instance=RequestContext(request))

def edit_image(request, folder_id):
    # TODO: implement edit_image view
    folder=None
    return render_to_response('image_filer/image_edit.html', {
            'folder':folder,
        }, context_instance=RequestContext(request))

def make_folder(request, folder_id=None):
    if folder_id:
        folder = Folder.objects.get(id=folder_id)
    else:
        folder = None
    if request.user.is_superuser:
        pass
    elif folder == None:
        # regular users may not add root folders
        return HttpResponseForbidden()
    elif not folder.has_add_children_permission(request):
        # the user does not have the permission to add subfolders
        return HttpResponseForbidden()
    
    if request.method == 'POST':
        new_folder_form = NewFolderForm(request.POST)
        if new_folder_form.is_valid():
            new_folder = new_folder_form.save(commit=False)
            new_folder.parent = folder
            new_folder.owner = request.user
            new_folder.save()
            return HttpResponseRedirect('')
    else:
        new_folder_form = NewFolderForm()
    return render_to_response('image_filer/include/new_folder_form.html', {
            'new_folder_form': new_folder_form,
    }, context_instance=RequestContext(request))

class UploadFileForm(forms.ModelForm):
    class Meta:
        model=Image
        #fields = ('file',)
        
from image_filer.utils.files import generic_handle_file

def upload(request, folder_id=None):
    """
    receives an upload from the flash uploader and fixes the session
    because of the missing cookie. Receives only one file at the time, 
    althow it may be a zip file, that will be unpacked.
    """
    
    # flashcookie-hack (flash does not submit the cookie, so we send the
    # django sessionid over regular post
    engine = __import__(settings.SESSION_ENGINE, {}, {}, [''])
    session_key = request.POST.get('cookieVar')
    request.session = engine.SessionStore(session_key)
    #print request.session.session_key, request.user
    if folder_id:
        folder = Folder.objects.get(id=folder_id)
    else:
        folder = None
    
    # check permissions
    if request.user.is_superuser:
        pass
    elif folder == None:
        # regular users may not add root folders
        return HttpResponseForbidden()
    elif not folder.has_add_children_permission(request):
        # the user does not have the permission to images to this folder
        print "bad perms"
        return HttpResponseForbidden()
    
    # upload and save the file
    if not request.method == 'POST':
        return HttpResponse("must be POST")
    original_filename = request.POST.get('Filename')
    file = request.FILES.get('Filedata')
    print request.FILES
    print original_filename, file
    bucket, was_bucket_created = Bucket.objects.get_or_create(user=request.user)
    print bucket
    files = generic_handle_file(file, original_filename)
    for ifile, iname in files:
        iext = os.path.splitext(iname)[1].lower()
        print "extension: ", iext
        if iext in ['.jpg','.jpeg','.png','.gif']:
            imageform = UploadFileForm({'original_filename':iname,'owner': request.user.pk}, {'file':ifile})
            if imageform.is_valid():
                print 'imageform is valid'
                image = imageform.save(commit=False)
                image.save()
                bi = BucketItem(bucket=bucket, file=image)
                bi.save()
                print image
            else:
                print imageform.errors
    return HttpResponse("ok")

def move_files_to_folder(request, bucket_id=None):
    folder = Folder.objects.get( id=request.GET.get('folder_id') )
    try:
        ids = request.GET.get('file_ids').split(',')
    except:
        ids = None
    if bucket_id:
        bucket = Bucket.objects.get(id=bucket_id)
        files = bucket.files.all()
    elif ids:
        files = Image.objects.filter(id__in=ids)
    else:
        return HttpResponse('nothing to do')
    for file in files:
        file.folder = folder
        file.save()
    return HttpResponse('ok')
    

def add_file_to_bucket(request):
    pass

def export_bucket(request):
    pass
