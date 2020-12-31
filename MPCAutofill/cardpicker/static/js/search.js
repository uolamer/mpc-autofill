// set up ajax to attach the CSRF token to all requests to the server
// lifted from https://docs.djangoproject.com/en/3.1/ref/csrf/#ajax
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}


const csrftoken = getCookie('csrftoken');


function csrfSafeMethod(method) {
    // these HTTP methods do not require CSRF protection
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}


$.ajaxSetup({
    beforeSend: function (xhr, settings) {
        if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    }
});


function search_api_multiple(drive_order, query, slot_ids, face, req_type = "normal") {
    // takes in a cardname and an array of slot numbers, queries elasticsearch for info on that
    // cardname, and returns the result - this wrapper function also handles grouping
    let group = 0;
    if (req_type === "back") {
        group = 1;
    } else if (slot_ids.length > 1) {
        group = max_group;
        max_group++;
    }
    let dom_ids = []
    for (let i = 0; i < slot_ids.length; i++) {
        dom_ids.push(
            search_api(
                drive_order,
                query,
                slot_ids[i],
                face,
                req_type,
                group
            )
        );
    }
    if (slot_ids.length > 0) {
        if (group === 1 && groups[group] !== undefined) {
            // this code should run when the common back group already exists but we have new cards to add to it
            // remove the first element (the right panel common cardback) from dom_ids, then smush the existing
            // ids and the new ids together
            dom_ids = dom_ids.slice(1);
            groups[group] = groups[group].concat(dom_ids);
        } else {
            groups[group] = dom_ids;

        }
    }
}


function search_api(drive_order, query, slot_id, face, req_type = "normal", group = 0) {
    // takes in a cardname and a single slot number, queries elasticsearch for info on that
    // cardname, and inserts the result into the review page (creating a div if necessary)
    let dom_id = "slot" + slot_id[0].toString() + "-" + face;

    $.post(
        '/ajax/search/',
        {
            'drive_order': drive_order,
            'query': query,
            'slots': slot_id[0].toString(),
            'dom_id': dom_id,
            'face': face,
            'req_type': req_type,
            'group': group,
            'selected_img': slot_id[1]
        },
        function (data) {
            // TODO clean up bc this is a bit shit atm - don't use a jquery identifier here?
            if ($('#' + dom_id).length < 1) {
                // create div element for this card to occupy with the appropriate classes
                let card_elem = document.createElement("div");
                card_elem.id = dom_id;
                card_elem.className = "card mpccard card-" + face;

                // because jquery is asynchronous, there's no guarantee that these will be created in the correct order
                // ensure they're ordered by slot number
                card_elem.style.order = slot_id[0];
                document.getElementById("card-container").appendChild(card_elem);

                // if this is a cardback elem, set it to display: none
                if (face === "back") {
                    card_elem.style.display = "none";
                }

                // start at opacity 0 so cards can fade in
                card_elem.style.opacity = "0";
            }

            // insert the returned data into this card's element
            $('#' + dom_id).html(data);
        },
        'html'
    );
    return dom_id
}


function insert_text() {
    let text = document.getElementById("id_card_list").value;

    $.post(
        '/ajax/text/',
        {
            'text': text,
            'offset': qty
        },
        function (data) {
            insert_data(data);
        },
        'json'
    );

    $('#textModal').modal('hide');
    return false;
}


function insert_xml() {
    // TODO: ajax running off the hook?

    // read the XML file as text, then do a POST request with the contents
    let xmlfiles = document.getElementById("xmlfile").files;
    if (xmlfiles.length > 0) {
        xmlfiles[0].text().then(text => $.post(
            '/ajax/xml/',
            {
                'xml': text,
                'offset': qty
            },
            function (data) {
                insert_data(data);
            },
            'json'
        ));
    }
}

function insert_data(data) {
    // switch to fronts if necessary
    if (!front_visible) {
        switchFaces();
    }
    // insert each card in the returned results into the DOM, and update qty & bracket
    for (let face in data.order) {
        for (let key in data.order[face]) {
            search_api_multiple(
                drive_order,
                key,
                data.order[face][key]["slots"],
                face,
                data.order[face][key]["req_type"]
            );
        }
    }

    // update qty and bracket
    qty += data.qty;
    update_qty(qty);
}