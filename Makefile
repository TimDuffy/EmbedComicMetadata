zip:
	rm -f 'Embed Comic Metadata.zip'
	zip -r 'Embed Comic Metadata.zip' * -x ".git" -x ".devcontainer" -x "test-config" -x "test-library"
