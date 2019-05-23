$(document).ready(function() {
  var $upload = $('#upload');
  var $status = $('#status');
  var $list = $('#list');
  var $template = $('#template');
  var $bar = $('#bar');
  var $delete = $('#delete');

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
      var $entry = $($.templates('#tmpl-asset').render(data));
      $list.prepend($entry);
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
      dataTransfer.dropEffect = 'copy';
    }
  });

  $upload.on('dragenter', function(event) {
    if (event.originalEvent.dataTransfer) {
      var dataTransfer = event.originalEvent.dataTransfer;
      $upload.addClass('alert-success');
      dataTransfer.dropEffect = 'copy';
      $upload.removeClass('alert-info');
    }
  });

  $upload.on('dragleave', function(event) {
    $upload.addClass('alert-info');
    $upload.removeClass('alert-success');
  });

  $upload.on('drop', function(event) {
    $upload.addClass('alert-info');
    $upload.removeClass('alert-success');
    event.preventDefault();
    if (event.originalEvent.dataTransfer) {
      var dataTransfer = event.originalEvent.dataTransfer;
      dataTransfer.dropEffect = 'copy';
      var files = new Array();
      for (var i = 0; i < dataTransfer.files.length; i++) {
        files.push(dataTransfer.files[i]);
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
          $list.addMedia(data.pk, data);
          $progress.remove();
        }).uploadProgress(function(event) {
          var percent = Math.round(event.loaded / file.size * 100);
          if (percent > 100) {
            percent = 100;
          }
          $progress.find('.progress-bar').css('width', percent + '%').find('span').text(file.name + ': ' + percent + '%');
        }).fail(function(event) {
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
