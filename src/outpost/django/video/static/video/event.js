$(document).ready(function() {
  var $upload = $('#upload');
  var $status = $('#status');
  var $list = $('#list');
  var $template = $('#template');
  var $bar = $('#bar');
  var $delete = $('#delete');
  var mimetypes = [
    'video/mp4',
    'video/webm',
    'audio/mpeg',
    'audio/aac',
    'audio/mp4',
    'audio/x-m4a',
  ];
  var allowed;

  $delete.confirm(
    $delete.data('title'),
    $.templates('#tmpl-confirm-delete').render(),
    function() {
      $delete.prop('disabled', true);
      $.ajax(
        window.location.href,
        {
          method: 'DELETE'
        }
      ).done(function() {
        window.location.replace($delete.data('return'));
      }).fail(function() {
        $delete.prop('disabled', false);
      });
    }
  );


  $.fn.addMedia = function(pk, data) {
    var $list = $(this);
    var add  = function(data) {
      console.log(data);
      var $entry = $($.templates('#tmpl-media').render(data));
      $list.prepend($entry);
      if (data.hasOwnProperty('preview')) {
        $entry.find('.panel-heading .glyphicon').remove();
        $entry.find('.panel-heading img').attr('src', data.preview);
        $entry.find('.panel-heading a').attr('href', data.preview);
      } else {
        $entry.find('.panel-heading img').remove();
      }
      var $delete = $entry.find('.delete')
      $delete.confirm(
        $delete.data('title'),
        $.templates('#tmpl-confirm-delete').render(),
        function() {
          $delete.prop('disabled', true);
          $.ajax(
            $upload.data('url') + data.pk + '/',
            {
              method: 'DELETE',
              dataType: 'json'
            }
          ).done(function() {
            $entry.remove();
            if ($list.children().length == 0) {
              $('#empty').show();
            }
          }).fail(function() {
            $delete.prop('disabled', false);
          });
        }
      );
      $entry.find('.download').attr('href', data.url);
      $entry.addClass('in');
    };
    $('#empty').hide();
    var list = this;
    if (data) {
      list.each(function() {
        add(data);
      });
    } else {
      $.ajax(
        $upload.data('url') + pk + '/',
        {
          method: 'GET',
          dataType: 'json'
        }
      ).done(function(data) {
        list.each(function() {
          add(data);
        });
      });
    }
  };

  $upload.on('dragover', function(event) {
    event.preventDefault();
    if (event.originalEvent.dataTransfer) {
      var dataTransfer = event.originalEvent.dataTransfer;
      if (allowed) {
        dataTransfer.dropEffect = 'copy';
      } else {
        dataTransfer.dropEffect = 'none';
      }
    }
  });

  $upload.on('dragenter', function(event) {
    if (event.originalEvent.dataTransfer) {
      var dataTransfer = event.originalEvent.dataTransfer;
      allowed = true;
      for (var i = 0; i < dataTransfer.items.length; i++) {
        if (mimetypes.indexOf(dataTransfer.items[i].type) < 0) {
          allowed = false;
        }
      }
      if (allowed) {
        $upload.addClass('alert-success');
        dataTransfer.dropEffect = 'copy';
      } else {
        $upload.addClass('alert-danger');
        dataTransfer.dropEffect = 'none';
      }
      $upload.removeClass('alert-info');
    }
  });

  $upload.on('dragleave', function(event) {
    $upload.addClass('alert-info');
    $upload.removeClass('alert-success');
    $upload.removeClass('alert-danger');
  });

  $upload.on('drop', function(event) {
    $upload.addClass('alert-info');
    $upload.removeClass('alert-success');
    $upload.removeClass('alert-danger');
    event.preventDefault();
    if (event.originalEvent.dataTransfer) {
      if (!allowed) {
        return;
      }
      var dataTransfer = event.originalEvent.dataTransfer;
      dataTransfer.dropEffect = 'copy';
      var files = new Array();
      for (var i = 0; i < dataTransfer.files.length; i++) {
        if (mimetypes.indexOf(dataTransfer.items[i].type) >= 0) {
          files.push(dataTransfer.files[i]);
        }
      }
      files.forEach(function(file) {
        var $progress = $($.templates('#tmpl-upload').render(file));
        $status.append($progress);
        $progress.find('.progress-bar span').text(file.name + ': 0%')
        var data = new FormData();
        data.append('file', file);
        var req = $.ajax(
          $upload.data('url'),
          {
            method: 'POST',
            processData: false,
            contentType: false,
            data: data
          }
        ).done(function(data) {
          console.log(data);
          $list.addMedia(data.pk, data);
          $progress.remove();
        }).uploadProgress(function(event) {
          var percent = Math.round(event.loaded / file.size * 100);
          if (percent > 100) {
            percent = 100;
          }
          $progress.find('.progress-bar').css('width', percent + '%').find('span').text(file.name + ': ' + percent + '%');
        }).fail(function(event) {
          console.log(event);
          $progress.find('.progress-bar').addClass('progress-bar-danger').css('width', '100%').find('span').text(event);
        });
        $progress.find('.cancel').on('click', function() {
          req.abort();
          $progress.remove();
        });
        $progress.addClass('in');
      });
    }
  });

});
